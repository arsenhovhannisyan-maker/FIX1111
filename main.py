import quickfix as fix
from datetime import datetime
from threading import Timer
from fastapi import FastAPI, HTTPException
import uvicorn
from contextlib import asynccontextmanager
from fix_md_session import FIXMarketDataApp
from fix_om_session import OrderSession
from data_store import market_data_store
from urllib.parse import unquote

sessions = {
    "md": {"app": None, "initiator": None, "ready": False},
    "om": {"app": None, "initiator": None, "ready": False}
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        settings = fix.SessionSettings("settings_md.cfg")
        sessions["md"]["app"] = FIXMarketDataApp()
        sessions["md"]["initiator"] = fix.SocketInitiator(
            sessions["md"]["app"],
            fix.FileStoreFactory(settings),
            settings,
            fix.FileLogFactory(settings)
        )
        sessions["md"]["initiator"].start()
        sessions["md"]["ready"] = True
        print("[MD] Session started")
    except Exception as e:
        print(f"[MD] Error: {e}")

    try:
        settings = fix.SessionSettings("settings_om.cfg")
        sessions["om"]["app"] = OrderSession()
        sessions["om"]["initiator"] = fix.SocketInitiator(
            sessions["om"]["app"],
            fix.FileStoreFactory(settings),
            settings,
            fix.FileLogFactory(settings)
        )
        sessions["om"]["initiator"].start()
        sessions["om"]["ready"] = True
        print("[OM] Session started")
    except Exception as e:
        print(f"[OM] Error: {e}")

    Timer(3.0, auto_subscribe).start()

    yield

    for name in ["md", "om"]:
        if sessions[name]["initiator"]:
            sessions[name]["initiator"].stop()

def auto_subscribe():
    if not sessions["md"]["ready"]:
        return

    instruments = ["EUR/USD", "GBP/USD", "USD/JPY", "USD/CAD"]

    for i, instrument in enumerate(instruments):
        Timer(i * 0.5 + 6.0, lambda sym=instrument: sessions["md"]["app"].send_market_data_request(sym)).start()
        print(f"[AUTO] Will subscribe to {instrument} in {i*0.5+6.0} seconds")

app = FastAPI(title="FIX Trading API", version="1.0", lifespan=lifespan)

@app.get("/market")
async def get_market_data():
    try:
        data = market_data_store.get_all()
        return {
            "status": "success",
            "data": data,
            "count": len(data),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(500, detail=f"Error getting market data: {str(e)}")

@app.get("/market/{symbol:path}")
async def get_symbol_data(symbol: str):
    decoded_symbol = unquote(symbol)
    data = market_data_store.get(decoded_symbol)
    if not data:
        possible_symbols = [
            decoded_symbol,
            decoded_symbol.replace('/', '_'),
            decoded_symbol.replace('_', '/')
        ]

        for sym in possible_symbols:
            data = market_data_store.get(sym)
            if data:
                break

        if not data:
            available = list(market_data_store.keys())
            raise HTTPException(
                404,
                detail=f"Symbol '{decoded_symbol}' not found. Available: {available}"
            )

    return {
        "status": "success",
        "symbol": decoded_symbol,
        "data": data,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/market/subscribe/{symbol:path}")
async def subscribe_symbol(symbol: str):
    if not sessions["md"]["ready"]:
        raise HTTPException(500, "MD session not ready")

    decoded_symbol = unquote(symbol)
    sessions["md"]["app"].send_market_data_request(decoded_symbol)
    return {"status": "subscribed", "symbol": decoded_symbol}

@app.post("/market/unsubscribe/{symbol:path}")
async def unsubscribe_symbol(symbol: str):
    if not sessions["md"]["ready"]:
        raise HTTPException(500, "MD session not ready")

    decoded_symbol = unquote(symbol)
    sessions["md"]["app"].send_market_data_unsubscribe(decoded_symbol)
    return {"status": "unsubscribed", "symbol": decoded_symbol}

@app.post("/order")
async def create_order(
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "LIMIT",
        price: float = None,
        time_in_force: str = "GTC"
):
    if not sessions["om"]["ready"]:
        raise HTTPException(500, "OM session not ready")

    om_app = sessions["om"]["app"]

    if not om_app.trading_session_open:
        raise HTTPException(400, "Trading session not open")

    side_fix = "1" if side.upper() in ["BUY", "B"] else "2"
    order_type_fix = "1" if order_type.upper() == "MARKET" else "2"

    tif_map = {"GTC": "1", "IOC": "3", "FOK": "4", "GTD": "6"}
    tif_fix = tif_map.get(time_in_force.upper(), "1")

    cl_ord_id = om_app.send_new_order_single(
        symbol=symbol,
        side=side_fix,
        quantity=quantity,
        price=price,
        order_type=order_type_fix,
        time_in_force=tif_fix
    )

    if not cl_ord_id:
        raise HTTPException(500, "Failed to send order")

    return {
        "cl_ord_id": cl_ord_id,
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "order_type": order_type,
        "time_in_force": time_in_force
    }

@app.get("/orders")
async def get_orders():
    if not sessions["om"]["ready"]:
        raise HTTPException(500, "OM session not ready")
    return sessions["om"]["app"].get_all_orders()

@app.post("/orders/{cl_ord_id}/cancel")
async def cancel_order(cl_ord_id: str):
    if not sessions["om"]["ready"]:
        raise HTTPException(500, "OM session not ready")

    if not sessions["om"]["app"].send_order_cancel_request(cl_ord_id):
        raise HTTPException(400, "Cancel failed")

    return {"status": "cancel_sent", "cl_ord_id": cl_ord_id}

@app.get("/status")
async def get_status():
    md_app = sessions["md"]["app"]
    om_app = sessions["om"]["app"]

    return {
        "market_data": {
            "ready": sessions["md"]["ready"],
            "connected": getattr(md_app, 'logon_sent', False) if md_app else False,
            "active": getattr(md_app, 'market_session_active', False) if md_app else False,
            "subscriptions": len(getattr(md_app, 'market_data_subscriptions', {})),
            "instruments_loaded": getattr(md_app, 'security_list_received', False),
            "instrument_count": len(getattr(md_app, 'security_instruments', []))
        },
        "order_session": {
            "ready": sessions["om"]["ready"],
            "connected": getattr(om_app, 'logon_sent', False) if om_app else False,
            "open": getattr(om_app, 'trading_session_open', False) if om_app else False,
            "orders": len(getattr(om_app, 'orders', {}))
        }
    }

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "market_data": "up" if sessions["md"]["ready"] else "down",
        "order_session": "up" if sessions["om"]["ready"] else "down"
    }

@app.get("/instruments")
async def get_instruments():
    if not sessions["md"]["ready"]:
        raise HTTPException(500, "MD session not ready")

    md_app = sessions["md"]["app"]
    return {
        "status": "success",
        "instruments": getattr(md_app, 'security_instruments', []),
        "count": len(getattr(md_app, 'security_instruments', []))
    }

@app.get("/security/definition/{symbol:path}")
async def get_security_definition(symbol: str):
    if not sessions["md"]["ready"]:
        raise HTTPException(500, "MD session not ready")

    decoded_symbol = unquote(symbol)
    req_id = sessions["md"]["app"].send_security_definition_request(decoded_symbol)
    return {"status": "request_sent", "symbol": decoded_symbol, "request_id": req_id}

@app.post("/instruments/refresh")
async def refresh_instruments():
    if not sessions["md"]["ready"]:
        raise HTTPException(500, "MD session not ready")

    req_id = sessions["md"]["app"].send_security_list_request()
    return {
        "status": "request_sent",
        "request_id": req_id
    }
@app.post("/instruments/refresh")
async def refresh_instruments():
    if not sessions["md"]["ready"]:
        raise HTTPException(500, "MD session not ready")

    req_id = sessions["md"]["app"].send_security_list_request()
    if not req_id:
        raise HTTPException(400, "SecurityListRequest not supported by counterparty")

    return {
        "status": "request_sent",
        "request_id": req_id
    }

if __name__ == "__main__":
    print("FIX Trading API Server")
    print("Port: 8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
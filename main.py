import quickfix as fix
from datetime import datetime
from threading import Timer
from fastapi import FastAPI, HTTPException
import uvicorn
from contextlib import asynccontextmanager
from fix_md_session import FIXApplication as MDApp
from fix_om_session import OrderSession as OMApp
from data_store import market_data_store
from urllib.parse import unquote

sessions = {
    "md": {"app": None, "initiator": None, "ready": False},
    "om": {"app": None, "initiator": None, "ready": False}
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    global sessions
    try:
        print("[INIT] Starting Market Data session...")
        md_settings = fix.SessionSettings("settings_md.cfg")
        sessions["md"]["app"] = MDApp()

        md_initiator = fix.SocketInitiator(
            sessions["md"]["app"],
            fix.FileStoreFactory(md_settings),
            md_settings,
            fix.FileLogFactory(md_settings)
        )
        md_initiator.start()
        sessions["md"]["initiator"] = md_initiator
        sessions["md"]["ready"] = True
        print("[MD] ✓ Market Data session started")
    except Exception as e:
        print(f"[MD] ✗ Error starting Market Data session: {e}")
        sessions["md"]["ready"] = False

    try:
        print("[INIT] Starting Order session...")
        om_settings = fix.SessionSettings("settings_om.cfg")
        sessions["om"]["app"] = OMApp()

        om_initiator = fix.SocketInitiator(
            sessions["om"]["app"],
            fix.FileStoreFactory(om_settings),
            om_settings,
            fix.FileLogFactory(om_settings)
        )
        om_initiator.start()
        sessions["om"]["initiator"] = om_initiator
        sessions["om"]["ready"] = True
        print("[OM] ✓ Order session started")
    except Exception as e:
        print(f"[OM] ✗ Error starting Order session: {e}")
        sessions["om"]["ready"] = False

    Timer(3.0, auto_subscribe_md).start()

    yield

    print("[INIT] Stopping sessions...")
    for name in ["md", "om"]:
        if sessions[name]["initiator"]:
            try:
                sessions[name]["initiator"].stop()
                print(f"[{name.upper()}] ✓ Session stopped")
            except Exception as e:
                print(f"[{name.upper()}] ✗ Error stopping session: {e}")

def auto_subscribe_md():
    if not sessions["md"]["ready"] or not sessions["md"]["app"]:
        print("[AUTO-SUB] Skipping - MD session not ready")
        return

    instruments = [
        "EUR/USD",
        "GBP/USD",
        "USD/CAD",
        "EUR/USD_ON",
        "GBP/USD_TN",
        "USD/CAD_TOM1W",
        "EUR/USD_2W"
    ]

    delay = 0.0
    for instrument in instruments:
        Timer(delay, lambda sym=instrument: subscribe_instrument(sym)).start()
        delay += 0.3

def subscribe_instrument(symbol: str):
    """Подписаться на инструмент"""
    if sessions["md"]["app"]:
        sessions["md"]["app"].send_market_data_request(symbol)
        print(f"[AUTO-SUB] ✓ Subscribed to {symbol}")

app = FastAPI(
    title="FIX Trading API",
    description="API для работы с FIX Market Data и Order Execution",
    version="1.0.0",
    lifespan=lifespan
)

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
        raise HTTPException(404, detail=f"Symbol {decoded_symbol} not found")

    return {
        "status": "success",
        "symbol": decoded_symbol,
        "data": data,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/market/subscribe/{symbol:path}")
async def subscribe_symbol(symbol: str):
    if not sessions["md"]["ready"] or not sessions["md"]["app"]:
        raise HTTPException(500, detail="Market Data session not ready")

    decoded_symbol = unquote(symbol)

    Timer(0.1, lambda: sessions["md"]["app"].send_market_data_request(decoded_symbol)).start()

    return {
        "status": "subscribed",
        "symbol": decoded_symbol,
        "message": f"Subscription request sent for {decoded_symbol}",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/market/unsubscribe/{symbol}")
async def unsubscribe_symbol(symbol: str):
    if not sessions["md"]["ready"] or not sessions["md"]["app"]:
        raise HTTPException(500, detail="Market Data session not ready")

    if hasattr(sessions["md"]["app"], 'send_market_data_unsubscribe'):
        sessions["md"]["app"].send_market_data_unsubscribe(symbol)
    else:
        sessions["md"]["app"].send_market_data_request(symbol, subscription_type="2")

    return {
        "status": "unsubscribed",
        "symbol": symbol,
        "message": f"Unsubscription request sent for {symbol}",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/order")
async def create_order(
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "LIMIT",
        price: float = None,
):
    if not sessions["om"]["ready"] or not sessions["om"]["app"]:
        raise HTTPException(500, detail="Order session not ready")

    om_app = sessions["om"]["app"]

    if not om_app.trading_session_open:
        raise HTTPException(400, detail="Trading session not open. Wait for TradingSessionStatus")

    side_fix = "1" if side.upper() in ["BUY", "B", "1"] else "2"

    order_type_map = {
        "MARKET": "1",
        "LIMIT": "2",
        "STOP": "3",
        "STOP_LIMIT": "4"
    }
    order_type_fix = order_type_map.get(order_type.upper(), "2")

    cl_ord_id = om_app.send_new_order_single(
        symbol=symbol,
        side=side_fix,
        quantity=quantity,
        price=price,
        order_type=order_type_fix,
    )

    if not cl_ord_id:
        raise HTTPException(500, detail="Failed to send order")

    return {
        "status": "sent",
        "cl_ord_id": cl_ord_id,
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "price": price,
        "order_type": order_type,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/orders")
async def get_orders():
    if not sessions["om"]["ready"] or not sessions["om"]["app"]:
        raise HTTPException(500, detail="Order session not ready")

    return sessions["om"]["app"].get_all_orders()

@app.get("/orders/{cl_ord_id}")
async def get_order(cl_ord_id: str):
    if not sessions["om"]["ready"] or not sessions["om"]["app"]:
        raise HTTPException(500, detail="Order session not ready")

    order_info = sessions["om"]["app"].get_order_info(cl_ord_id)
    if not order_info:
        raise HTTPException(404, detail=f"Order {cl_ord_id} not found")

    return order_info

@app.post("/orders/{cl_ord_id}/cancel")
async def cancel_order(cl_ord_id: str):
    if not sessions["om"]["ready"] or not sessions["om"]["app"]:
        raise HTTPException(500, detail="Order session not ready")

    om_app = sessions["om"]["app"]

    if not om_app.trading_session_open:
        raise HTTPException(400, detail="Trading session not open")

    order_info = om_app.get_order_info(cl_ord_id)
    if not order_info:
        raise HTTPException(404, detail=f"Order {cl_ord_id} not found")

    success = om_app.send_order_cancel_request(
        cl_ord_id,
        order_info.get("symbol"),
        order_info.get("side")
    )

    if not success:
        raise HTTPException(500, detail="Failed to send cancel request")

    return {
        "status": "cancel_sent",
        "cl_ord_id": cl_ord_id,
        "message": "Cancel request sent successfully",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/orders/{cl_ord_id}/status")
async def request_order_status(cl_ord_id: str):
    if not sessions["om"]["ready"] or not sessions["om"]["app"]:
        raise HTTPException(500, detail="Order session not ready")

    om_app = sessions["om"]["app"]

    if not om_app.trading_session_open:
        raise HTTPException(400, detail="Trading session not open")

    success = om_app.send_order_status_request(cl_ord_id)

    if not success:
        raise HTTPException(500, detail="Failed to send status request")

    return {
        "status": "status_request_sent",
        "cl_ord_id": cl_ord_id,
        "message": "Status request sent successfully",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/executions")
async def get_executions():
    if not sessions["om"]["ready"] or not sessions["om"]["app"]:
        raise HTTPException(500, detail="Order session not ready")

    return sessions["om"]["app"].get_execution_history()

@app.get("/status")
async def get_status():
    status_info = {
        "timestamp": datetime.now().isoformat(),
        "sessions": {}
    }

    md_status = {
        "ready": sessions["md"]["ready"],
        "connected": False,
        "active": False,
        "security_list_received": False,
        "instruments_count": 0,
        "subscriptions_count": 0
    }

    if sessions["md"]["ready"] and sessions["md"]["app"]:
        md_app = sessions["md"]["app"]
        md_status["connected"] = getattr(md_app, 'logon_sent', False)
        md_status["active"] = getattr(md_app, 'trading_session_active', False)
        md_status["security_list_received"] = getattr(md_app, 'security_list_received', False)
        md_status["instruments_count"] = len(getattr(md_app, 'security_instruments', []))
        md_status["subscriptions_count"] = len(getattr(md_app, 'market_data_subscriptions', {}))

    status_info["sessions"]["market_data"] = md_status

    om_status = {
        "ready": sessions["om"]["ready"],
        "connected": False,
        "trading_session_open": False,
        "orders_count": 0,
        "executions_count": 0
    }

    if sessions["om"]["ready"] and sessions["om"]["app"]:
        om_app = sessions["om"]["app"]
        om_status["connected"] = getattr(om_app, 'logon_sent', False)
        om_status["trading_session_open"] = getattr(om_app, 'trading_session_open', False)
        om_status["orders_count"] = len(om_app.order_store)
        om_status["executions_count"] = len(om_app.execution_reports)

    status_info["sessions"]["order_session"] = om_status

    return status_info

@app.get("/health")
async def health_check():
    md_ok = sessions["md"]["ready"] and sessions["md"]["app"] and getattr(sessions["md"]["app"], 'logon_sent', False)
    om_ok = sessions["om"]["ready"] and sessions["om"]["app"] and getattr(sessions["om"]["app"], 'logon_sent', False)

    overall_status = "healthy" if md_ok and om_ok else "degraded"

    return {
        "status": overall_status,
        "market_data": "up" if md_ok else "down",
        "order_session": "up" if om_ok else "down",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/security/list")
async def get_security_list():
    if not sessions["md"]["ready"] or not sessions["md"]["app"]:
        raise HTTPException(500, detail="Market Data session not ready")

    md_app = sessions["md"]["app"]

    return {
        "status": "success",
        "security_list_received": md_app.security_list_received,
        "instruments": md_app.security_instruments,
        "count": len(md_app.security_instruments),
        "timestamp": datetime.now().isoformat()
    }

@app.post("/security/request")
async def request_security_list():
    if not sessions["md"]["ready"] or not sessions["md"]["app"]:
        raise HTTPException(500, detail="Market Data session not ready")

    Timer(0.1, lambda: sessions["md"]["app"].send_security_list_request()).start()

    return {
        "status": "request_sent",
        "message": "SecurityList request sent",
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    print("=" * 50)
    print("FIX Trading API Server")
    print("=" * 50)
    print("Configurations:")
    print("  Market Data: settings_md.cfg")
    print("  Order Session: settings_om.cfg")
    print(f"  Port: 8000")
    print("\nAvailable Endpoints:")
    print("\n  Market Data:")
    print("    GET  /market               - Get all market data")
    print("    GET  /market/{symbol}      - Get symbol data")
    print("    POST /market/subscribe/{symbol} - Subscribe to symbol")
    print("    POST /market/unsubscribe/{symbol} - Unsubscribe from symbol")

    print("\n  Order Session:")
    print("    POST /order                - Create new order")
    print("    GET  /orders               - Get all orders")
    print("    GET  /orders/{id}          - Get order details")
    print("    POST /orders/{id}/cancel   - Cancel order")
    print("    POST /orders/{id}/status   - Request order status")
    print("    GET  /executions           - Get execution history")

    print("\n  System:")
    print("    GET  /status               - Get system status")
    print("    GET  /health               - Health check")
    print("=" * 50)

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
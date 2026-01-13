import quickfix as fix
from datetime import datetime
from threading import Timer
from fastapi import FastAPI, HTTPException
import uvicorn
from contextlib import asynccontextmanager
from fix_md_session import FIXApplication as MDApp
from fix_om_session import OrderSession as OMApp
from data_store import market_data_store

sessions = {
    "md": {"app": None, "initiator": None},
    "om": {"app": None, "initiator": None}
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
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
        print("[MD] Session started")
    except Exception as e:
        print(f"[MD] Error: {e}")

    try:
        # Order Session
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
        print("[OM] Session started")
    except Exception as e:
        print(f"[OM] Error: {e}")

    yield

    for name in ["md", "om"]:
        if sessions[name]["initiator"]:
            sessions[name]["initiator"].stop()
            print(f"[{name.upper()}] Stopped")

app = FastAPI(lifespan=lifespan)

# ========== Market Data Endpoints ==========
@app.get("/md")
async def get_md():
    try:
        data = market_data_store.get_all()
        count = len(data) if isinstance(data, dict) else 0
    except AttributeError:
        data = {}
        count = 0

    return {
        "data": data,
        "count": count
    }

@app.get("/md/{symbol}")
async def get_md_symbol(symbol: str):
    # Используем метод get() класса ThreadSafeMarketData
    data = market_data_store.get(symbol)
    return data if data else {"error": "Not found"}

@app.post("/md/subscribe/{symbol}")
async def subscribe_md(symbol: str):
    if md_app := sessions["md"]["app"]:
        Timer(0.1, lambda: md_app.send_market_data_request(symbol)).start()
        return {"status": "subscribed", "symbol": symbol}
    raise HTTPException(500, "MD session not ready")

# ========== Order Session Endpoints ==========
@app.post("/order")
async def create_order(symbol: str, side: str, qty: float, price: float = None):
    """Создать новый ордер"""
    if not (om_app := sessions["om"]["app"]):
        raise HTTPException(500, "OM session not ready")

    if not om_app.logon_sent:
        raise HTTPException(400, "Not logged in")

    if not om_app.trading_session_open:  # ← ДОБАВЬ ЭТУ ПРОВЕРКУ
        raise HTTPException(400, "Trading session not open")

    side_fix = "1" if side.lower() in ["buy", "1"] else "2"
    order_type = "2" if price else "1"

    cl_ord_id = om_app.send_new_order_single(
        symbol=symbol,
        side=side_fix,
        quantity=qty,
        price=price,
        order_type=order_type
    )

    if cl_ord_id:
        return {
            "status": "sent",
            "cl_ord_id": cl_ord_id,
            "message": f"Order {cl_ord_id} sent successfully"
        }
    raise HTTPException(500, "Failed to send order")

# ========== НОВЫЙ ЭНДПОИНТ: Тестовый ордер ==========
@app.post("/orders/test")
async def send_test_order():
    """Отправить тестовый ордер"""
    if not (om_app := sessions["om"]["app"]):
        raise HTTPException(500, "OM session not ready")

    if not om_app.logon_sent:
        raise HTTPException(400, "Not logged in")

    if not om_app.trading_session_open:
        raise HTTPException(400, "Trading session not open")

    # Отправляем тестовый ордер
    om_app.send_test_order()

    return {
        "status": "test_order_sent",
        "message": "Test order has been sent",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/orders")
async def get_orders():
    if om_app := sessions["om"]["app"]:
        return om_app.order_store
    raise HTTPException(500, "OM session not ready")

@app.post("/orders/{cl_ord_id}/cancel")
async def cancel_order(cl_ord_id: str):
    if not (om_app := sessions["om"]["app"]):
        raise HTTPException(500, "OM session not ready")

    order = om_app.get_order_info(cl_ord_id)
    if not order:
        raise HTTPException(404, "Order not found")

    success = om_app.send_order_cancel_request(
        cl_ord_id,
        order.get("symbol", "EUR/USD"),
        order.get("side", "1")
    )

    return {"status": "cancel_sent" if success else "failed"}

@app.get("/executions")
async def get_executions():
    if om_app := sessions["om"]["app"]:
        return om_app.execution_reports
    raise HTTPException(500, "OM session not ready")

# ========== Status Endpoints ==========
@app.get("/status")
async def status():
    result = {}

    if md_app := sessions["md"]["app"]:
        try:
            instruments_count = market_data_store.get_count()
        except AttributeError:
            try:
                instruments_count = len(market_data_store._data)
            except:
                instruments_count = 0

        result["md"] = {
            "connected": md_app.logon_sent,
            "active": md_app.trading_session_active,
            "instruments": instruments_count  # ← ИСПРАВЛЕНО
        }

    if om_app := sessions["om"]["app"]:
        result["om"] = {
            "connected": om_app.logon_sent,
            "trading_session_open": om_app.trading_session_open,
            "orders": len(om_app.order_store),
            "executions": len(om_app.execution_reports)
        }

    return result

@app.get("/health")
async def health():
    md_ok = sessions["md"]["app"] and sessions["md"]["app"].logon_sent
    om_ok = sessions["om"]["app"] and sessions["om"]["app"].logon_sent

    return {
        "status": "ok" if md_ok or om_ok else "degraded",
        "md": "up" if md_ok else "down",
        "om": "up" if om_ok else "down",
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    print("FIX API Server starting...")
    print("MD: settings_md.cfg")
    print("OM: settings_om.cfg")
    print("Port: 8000")
    print("\nAvailable endpoints:")
    print("  POST /order           - Create new order")
    print("  POST /orders/test     - Send test order")
    print("  GET  /orders          - Get all orders")
    print("  POST /orders/{id}/cancel - Cancel order")
    print("  GET  /status          - Get status")
    print("  GET  /health          - Health check")
    uvicorn.run(app, host="0.0.0.0", port=8000)
import quickfix as fix
from datetime import datetime
from threading import Timer
from fastapi import FastAPI
import uvicorn
from contextlib import asynccontextmanager
from fix_app import FIXApplication, market_data_store

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[SYSTEM] Starting FIX...")
    try:
        settings = fix.SessionSettings("settings.cfg")
        application = FIXApplication()
        storeFactory = fix.FileStoreFactory(settings)
        logFactory = fix.FileLogFactory(settings)
        initiator = fix.SocketInitiator(application, storeFactory, settings, logFactory)
        initiator.start()
        app.state.initiator = initiator
        app.state.application = application
    except Exception as e:
        print(f"[ERROR] Start: {e}")

    yield

    print("[SYSTEM] Stopping FIX...")
    if hasattr(app.state, 'initiator'):
        app.state.initiator.stop()

app = FastAPI(lifespan=lifespan)

@app.get("/market-data")
async def get_market_data():
    return {
        "status": "connected" if market_data_store else "waiting",
        "timestamp": datetime.now().isoformat(),
        "instruments_count": len(market_data_store),
        "data": market_data_store
    }

@app.get("/market-data/{symbol}")
async def get_market_data_symbol(symbol: str):
    if symbol in market_data_store:
        return market_data_store[symbol]
    return {
        "error": f"Instrument {symbol} not found",
        "available_instruments": list(market_data_store.keys())
    }

@app.get("/status")
async def get_status():
    if hasattr(app.state, 'application'):
        app_obj = app.state.application
        return {
            "session_id": str(app_obj.session_id) if app_obj.session_id else None,
            "logon_sent": app_obj.logon_sent,
            "trading_session_active": app_obj.trading_session_active,
            "market_data_instruments": len(market_data_store),
            "available_instruments": list(market_data_store.keys()),
            "timestamp": datetime.now().isoformat()
        }
    return {"status": "not_initialized"}

@app.post("/subscribe/{symbol}")
async def subscribe_symbol(symbol: str):
    if hasattr(app.state, 'application'):
        app_obj = app.state.application
        if app_obj.trading_session_active and app_obj.session_id:
            Timer(0.1, lambda: app_obj.send_market_data_request(symbol)).start()
            return {
                "status": "subscription_scheduled",
                "symbol": symbol,
                "message": f"Subscription to {symbol} scheduled"
            }
        else:
            return {
                "status": "error",
                "message": "FIX session not active"
            }
    return {"status": "not_initialized"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
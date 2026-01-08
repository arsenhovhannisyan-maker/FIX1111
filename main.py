import quickfix as fix
from datetime import datetime
from threading import Timer
from fastapi import FastAPI
import uvicorn
from contextlib import asynccontextmanager

market_data_store = {}

class FIXApplication(fix.Application):
    def __init__(self):
        super().__init__()
        self.session_id = None
        self.logon_sent = False

    def onCreate(self, sessionID):
        self.session_id = sessionID
        print(f"[SESSION] Session: {sessionID}")

    def onLogon(self, sessionID):
        print("[SESSION] Logon OK")
        self.logon_sent = True

    def onLogout(self, sessionID):
        print("[SESSION] Logout")
        self.logon_sent = False

    def toAdmin(self, message, sessionID):
        msg_type = fix.MsgType()
        message.getHeader().getField(msg_type)

        if msg_type.getValue() == fix.MsgType_Logon:
            print("[ADMIN] Preparing Logon")

            # Добавляем пароль
            message.setField(fix.Password('Df2Hy8nM'))

            # Пытаемся установить ResetSeqNumFlag в N если есть
            try:
                if message.isSetField(fix.ResetSeqNumFlag()):
                    message.setField(fix.ResetSeqNumFlag('N'))
            except:
                pass

            print("[ADMIN] Logon prepared")

    def fromAdmin(self, message, sessionID):
        msg_type = fix.MsgType()
        message.getHeader().getField(msg_type)
        msg_type_val = msg_type.getValue()

        print(f"[ADMIN] Recv: {msg_type_val}")

        if msg_type_val == fix.MsgType_TradingSessionStatus:
            print("[SESSION] Trading session active")
            Timer(2.0, self.subscribe).start()

        elif msg_type_val == fix.MsgType_Logout:
            try:
                text = fix.Text()
                if message.isSetField(text):
                    message.getField(text)
                    print(f"[SESSION] Logout reason: {text.getValue()}")
            except:
                pass

    def fromApp(self, message, sessionID):
        msg_type = fix.MsgType()
        message.getHeader().getField(msg_type)
        msg_type_val = msg_type.getValue()

        print(f"[APP] Recv: {msg_type_val}")

        if msg_type_val == "2":  # ResendRequest
            self.handleResendRequest(message, sessionID)
        elif msg_type_val == "h":  # Trading Session Status
            print("[APP] TradingSessionStatus received")
            # Теперь можно начинать торговлю
        else:
            print(f"[APP] Unhandled message type: {msg_type_val}")

    def process_snapshot(self, message):
        try:
            symbol = fix.Symbol()
            message.getField(symbol)
            sym = symbol.getValue()

            no_entries = fix.NoMDEntries()
            message.getField(no_entries)
            count = no_entries.getValue()

            bids = []
            asks = []

            for i in range(1, count + 1):
                group = fix.Group(268, 269)
                message.getGroup(i, group)

                entry_type = fix.MDEntryType()
                price = fix.MDEntryPx()
                size = fix.MDEntrySize()

                group.getField(entry_type)
                group.getField(price)
                group.getField(size)

                entry = {"price": price.getValue(), "size": size.getValue()}

                if entry_type.getValue() == '0':
                    bids.append(entry)
                elif entry_type.getValue() == '1':
                    asks.append(entry)

            market_data_store[sym] = {
                "symbol": sym,
                "timestamp": datetime.now().isoformat(),
                "bids": bids,
                "asks": asks
            }
            print(f"[DATA] {sym}: {len(bids)} bids, {len(asks)} asks")

        except Exception as e:
            print(f"[ERROR] Process: {e}")

    def subscribe(self):
        if not self.session_id:
            return

        try:
            self.send_sub("EUR/USD", "EURUSD001")
            Timer(1.0, lambda: self.send_sub("GBP/USD", "GBPUSD001")).start()
        except Exception as e:
            print(f"[ERROR] Subscribe: {e}")

    def send_sub(self, symbol, req_id):
        try:
            message = fix.Message()
            header = message.getHeader()
            header.setField(fix.MsgType("V"))

            message.setField(fix.MDReqID(req_id))
            message.setField(fix.SubscriptionRequestType('1'))
            message.setField(fix.MarketDepth(0))
            message.setField(fix.MDUpdateType('0'))

            message.setField(fix.NoRelatedSym(1))
            symbol_group = fix.Group(146, 55)
            symbol_group.setField(fix.Symbol(symbol))
            message.addGroup(1, symbol_group)

            message.setField(fix.NoMDEntryTypes(2))
            bid_group = fix.Group(267, 269)
            bid_group.setField(fix.MDEntryType('0'))
            message.addGroup(1, bid_group)

            ask_group = fix.Group(267, 269)
            ask_group.setField(fix.MDEntryType('1'))
            message.addGroup(2, ask_group)

            print(f"[SEND] Subscribe to {symbol}")
            fix.Session.sendToTarget(message, self.session_id)

        except Exception as e:
            print(f"[ERROR] Send: {e}")

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
        "data": market_data_store
    }

@app.get("/status")
async def get_status():
    if hasattr(app.state, 'application'):
        app_obj = app.state.application
        return {
            "session_id": str(app_obj.session_id) if app_obj.session_id else None,
            "logon_sent": app_obj.logon_sent,
            "market_data": len(market_data_store)
        }
    return {"status": "not_initialized"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
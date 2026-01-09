import quickfix as fix
import quickfix44 as fix44
from datetime import datetime
from threading import Timer

market_data_store = {}

class FIXApplication(fix.Application):
    def __init__(self):
        super().__init__()
        self.session_id = None
        self.logon_sent = False
        self.trading_session_active = False
        self.market_data_subscriptions = {}

    def onCreate(self, sessionID):
        self.session_id = sessionID
        print(f"[SESSION] Session: {sessionID}")

    def onLogon(self, sessionID):
        print("[SESSION] Logon OK")
        self.logon_sent = True

    def onLogout(self, sessionID):
        print("[SESSION] Logout")
        self.logon_sent = False
        self.trading_session_active = False

    def toAdmin(self, message, sessionID):
        msg_type = fix.MsgType()
        message.getHeader().getField(msg_type)

        if msg_type.getValue() == fix.MsgType_Logon:
            print("[ADMIN] Preparing Logon")
            message.setField(fix.Password('Df2Hy8nM'))
            try:
                message.setField(fix.BoolField(141, True))
            except Exception as e:
                print(f"[WARN] Could not set ResetSeqNumFlag: {e}")

            print("[ADMIN] Logon prepared")

    def fromAdmin(self, message, sessionID):
        msg_type = fix.MsgType()
        message.getHeader().getField(msg_type)
        msg_type_val = msg_type.getValue()

        print(f"[ADMIN] Recv: {msg_type_val}")

        try:
            if msg_type_val == "5":
                text = fix.Text()
                if message.isSetField(text):
                    message.getField(text)
                    print(f"[SESSION] Logout reason: {text.getValue()}")
        except Exception as e:
            print(f"[ERROR] Admin message {msg_type_val}: {e}")

    def fromApp(self, message, sessionID):
        msg_type = fix.MsgType()
        message.getHeader().getField(msg_type)
        msg_type_val = msg_type.getValue()

        print(f"[APP] Recv: {msg_type_val}")

        try:
            if msg_type_val == "h":
                self.processTradingSessionStatus(message)
            elif msg_type_val == "W":
                self.processMarketDataSnapshot(message)
            elif msg_type_val == "X":
                self.processMarketDataIncremental(message)
            elif msg_type_val == "Y":
                self.processMarketDataRequestReject(message)
            elif msg_type_val == "i":
                pass
            elif msg_type_val == "AG":
                pass
            elif msg_type_val == "Z":
                pass
            elif msg_type_val == "y":
                self.processSecurityList(message)
            elif msg_type_val == "d":
                self.processSecurityDefinition(message)
            elif msg_type_val == "8":
                self.processExecutionReport(message)
            elif msg_type_val == "BN":
                pass
            elif msg_type_val == "9":
                pass
            elif msg_type_val == "AE":
                pass
            elif msg_type_val == "AQ":
                pass
            elif msg_type_val == "j":
                pass
            elif msg_type_val == "3":
                pass
            elif msg_type_val == "4":
                self.processSequenceReset(message)
            elif msg_type_val == "5":
                pass
            elif msg_type_val == "0":
                pass
            elif msg_type_val == "1":
                pass
            else:
                print(f"[APP] Unhandled message type: {msg_type_val}")

        except Exception as e:
            print(f"[ERROR] Processing message {msg_type_val}: {e}")


    def processTradingSessionStatus(self, message):
        try:
            trading_session_id = fix.StringField(336)
            trad_sess_status = fix.CharField(340)

            if not message.isSetField(trading_session_id):
                print("[APP] TradingSessionID not found in message")
                return

            if not message.isSetField(trad_sess_status):
                print("[APP] TradingSessionStatus not found in message")
                return

            message.getField(trading_session_id)
            message.getField(trad_sess_status)

            session_type = trading_session_id.getValue()
            status_code = trad_sess_status.getValue()

            status_map = {
                "1": "Halted",
                "2": "Open",
                "3": "Closed",
                "4": "Pre-Open",
                "5": "Pre-Close"
            }

            status_text = status_map.get(status_code, f"Unknown ({status_code})")

            print(f"[APP] TradingSessionStatus: {session_type} - {status_text}")

            if session_type == "Market Data":
                if status_code == "2":
                    self.trading_session_active = True
                    print("[APP] Market Data session is OPEN")
                    Timer(2.0, self.subscribe_all).start()
                else:
                    self.trading_session_active = False
                    print(f"[APP] Market Data session NOT available: {status_text}")

        except Exception as e:
            print(f"[ERROR] Processing TradingSessionStatus: {e}")

    def processSequenceReset(self, message):
        try:
            gap_fill_flag = fix.GapFillFlag()
            new_seq_no = fix.NewSeqNo()

            if message.isSetField(gap_fill_flag):
                message.getField(gap_fill_flag)
                gap_fill = gap_fill_flag.getValue()
            else:
                gap_fill = 'N'

            if message.isSetField(new_seq_no):
                message.getField(new_seq_no)
                seq_no = new_seq_no.getValue()
                print(f"[APP] SequenceReset: GapFill={gap_fill}, NewSeqNo={seq_no}")

        except Exception as e:
            print(f"[ERROR] Processing SequenceReset: {e}")

    def processMarketDataSnapshot(self, message):
        try:
            symbol = fix.Symbol()
            md_req_id = fix.MDReqID()

            message.getField(symbol)
            message.getField(md_req_id)

            sym = symbol.getValue()
            req_id = md_req_id.getValue()

            print(f"[DATA] Snapshot for {sym} (ReqID: {req_id})")

            self.market_data_subscriptions[sym] = req_id

            no_entries = fix.NoMDEntries()
            if not message.isSetField(no_entries):
                print(f"[DATA] No entries for {sym}")
                market_data_store[sym] = {
                    "symbol": sym,
                    "bids": [],
                    "asks": [],
                    "last_update": datetime.now().isoformat()
                }
                return

            message.getField(no_entries)
            count = no_entries.getValue()

            bids = []
            asks = []

            group = fix44.MarketDataSnapshotFullRefresh().NoMDEntries()

            for i in range(1, count + 1):
                message.getGroup(i, group)

                entry_type = fix.MDEntryType()
                price = fix.MDEntryPx()
                size = fix.MDEntrySize()

                if group.isSetField(entry_type):
                    group.getField(entry_type)
                    entry_type_val = entry_type.getValue()

                    price_val = 0.0
                    size_val = 0.0

                    if group.isSetField(price):
                        group.getField(price)
                        price_val = float(price.getValue())

                    if group.isSetField(size):
                        group.getField(size)
                        size_val = float(size.getValue())

                    entry = {
                        "price": price_val,
                        "size": size_val
                    }

                    if entry_type_val == '0':
                        bids.append(entry)
                    elif entry_type_val == '1':
                        asks.append(entry)

            market_data_store[sym] = {
                "symbol": sym,
                "timestamp": datetime.now().isoformat(),
                "bids": sorted(bids, key=lambda x: x["price"], reverse=True),
                "asks": sorted(asks, key=lambda x: x["price"]),
                "last_update": datetime.now().isoformat()
            }

            print(f"[DATA] {sym}: {len(bids)} bids, {len(asks)} asks")

        except Exception as e:
            print(f"[ERROR] Processing snapshot: {e}")

    def processMarketDataIncremental(self, message):
        try:
            md_req_id = fix.MDReqID()
            message.getField(md_req_id)
            symbol = None

            no_entries = fix.NoMDEntries()
            message.getField(no_entries)
            count = no_entries.getValue()

            for i in range(1, count + 1):
                group = fix44.MarketDataIncrementalRefresh().NoMDEntries()
                message.getGroup(i, group)

                md_update_action = fix.MDUpdateAction()
                entry_type = fix.MDEntryType()
                price = fix.MDEntryPx()
                size = fix.MDEntrySize()
                sym_field = fix.Symbol()

                if group.isSetField(sym_field):
                    group.getField(sym_field)
                    symbol = sym_field.getValue()

                if symbol not in market_data_store:
                    market_data_store[symbol] = {"symbol": symbol, "bids": [], "asks": [], "last_update": None}

                group.getField(md_update_action)
                group.getField(entry_type)
                group.getField(price)
                group.getField(size)

                action = md_update_action.getValue()
                entry_type_val = entry_type.getValue()
                price_val = float(price.getValue())
                size_val = float(size.getValue())

                target_list = market_data_store[symbol]["bids"] if entry_type_val == '0' else market_data_store[symbol]["asks"]

                if action == '0':  # New
                    target_list.append({"price": price_val, "size": size_val})
                elif action == '1':  # Change
                    for entry in target_list:
                        if entry["price"] == price_val:
                            entry["size"] = size_val
                            break
                elif action == '2':  # Delete
                    target_list[:] = [entry for entry in target_list if entry["price"] != price_val]

            # Sort book
            market_data_store[symbol]["bids"] = sorted(market_data_store[symbol]["bids"], key=lambda x: x["price"], reverse=True)
            market_data_store[symbol]["asks"] = sorted(market_data_store[symbol]["asks"], key=lambda x: x["price"])
            market_data_store[symbol]["last_update"] = datetime.now().isoformat()

            print(f"[DATA] Incremental update for {symbol}")

        except Exception as e:
            print(f"[ERROR] Processing incremental: {e}")

    def processMarketDataRequestReject(self, message):
        try:
            md_req_id = fix.MDReqID()
            text = fix.Text()

            message.getField(md_req_id)

            reject_text = "No reason provided"
            if message.isSetField(text):
                message.getField(text)
                reject_text = text.getValue()

            print(f"[REJECT] MarketDataRequest {md_req_id.getValue()} rejected: {reject_text}")

        except Exception as e:
            print(f"[ERROR] Processing reject: {e}")

    def processSecurityList(self, message):
        try:
            print("[DATA] Received Security List")
        except Exception as e:
            print(f"[ERROR] Processing security list: {e}")

    def processSecurityDefinition(self, message):
        try:
            print("[DATA] Received Security Definition")
        except Exception as e:
            print(f"[ERROR] Processing security definition: {e}")

    def processExecutionReport(self, message):
        try:
            symbol = fix.Symbol()
            ord_status = fix.OrdStatus()
            exec_type = fix.ExecType()

            message.getField(symbol)
            message.getField(ord_status)
            message.getField(exec_type)

            print(f"[TRADE] ExecutionReport for {symbol.getValue()}: "
                  f"OrdStatus={ord_status.getValue()}, ExecType={exec_type.getValue()}")
        except Exception as e:
            print(f"[ERROR] Processing execution report: {e}")

    def subscribe_all(self):
        if not self.session_id or not self.trading_session_active:
            print("[WARN] Cannot subscribe - session not active")
            return

        instruments = ["EUR/USD", "GBP/USD", "USD/JPY", "EUR/GBP"]

        for i, symbol in enumerate(instruments):
            try:
                delay = i * 1.0
                Timer(delay, lambda sym=symbol: self.send_market_data_request(sym)).start()
                print(f"[SEND] Scheduled subscription to {symbol} in {delay}s")
            except Exception as e:
                print(f"[ERROR] Scheduling subscription for {symbol}: {e}")

    def send_market_data_request(self, symbol):
        try:
            if not self.session_id or not self.trading_session_active:
                return

            md_req_id = f"MD_{symbol.replace('/', '')}_{datetime.now().strftime('%H%M%S')}"

            message = fix44.MarketDataRequest()
            message.setField(fix.MDReqID(md_req_id))
            message.setField(fix.SubscriptionRequestType('1'))
            message.setField(fix.MarketDepth(1))
            message.setField(fix.MDUpdateType(1))

            related_sym_group = fix44.MarketDataRequest.NoRelatedSym()
            related_sym_group.setField(fix.Symbol(symbol))
            message.addGroup(related_sym_group)

            entry_types = ['0', '1']
            for et in entry_types:
                md_entry_group = fix44.MarketDataRequest.NoMDEntryTypes()
                md_entry_group.setField(fix.MDEntryType(et))
                message.addGroup(md_entry_group)

            fix.Session.sendToTarget(message, self.session_id)

            print(f"[SEND] Subscribed to {symbol}")

        except Exception as e:
            print(f"[ERROR] Sending MarketDataRequest for {symbol}: {e}")

    def toApp(self, message, sessionID):
        msg_type = fix.MsgType()
        message.getHeader().getField(msg_type)
        msg_type_val = msg_type.getValue()

        print(f"[APP] Send: {msg_type_val}")

import quickfix as fix
import quickfix44 as fix44
from threading import Timer
from datetime import datetime, timedelta

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
        Timer(1.0, self.send_security_list_request).start()

    def send_security_list_request(self):
        try:
            msg = fix44.SecurityListRequest()
            msg.setField(fix.SecurityReqID(f"SEC_{datetime.now().strftime('%H%M%S')}"))
            msg.setField(fix.SecurityListRequestType(0))  # 0 = All securities
            fix.Session.sendToTarget(msg, self.session_id)
            print("[SEND] SecurityListRequest sent")
        except Exception as e:
            print(f"[ERROR] Sending SecurityListRequest: {e}")

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
            elif msg_type_val == "S":
                self.processQuote(message)
            elif msg_type_val == "AG":
                self.processQuoteRequestReject(message)
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
                market_data_store[sym] = {"symbol": sym, "bids": [], "asks": [], "last_update": datetime.now().isoformat()}
                print(f"[DATA] No entries for {sym}")
                return

            message.getField(no_entries)
            count = no_entries.getValue()

            bids, asks = [], []
            group = fix44.MarketDataSnapshotFullRefresh.NoMDEntries()

            for i in range(1, count + 1):
                message.getGroup(i, group)

                entry_type = fix.MDEntryType()
                if not group.isSetField(entry_type):
                    continue
                group.getField(entry_type)
                entry_type_val = entry_type.getValue()

                price_val = 0.0
                size_val = 0.0

                price_field = fix.MDEntryPx()
                if group.isSetField(price_field):
                    group.getField(price_field)
                    try:
                        price_val = float(price_field.getValue())
                    except ValueError:
                        price_val = 0.0

                size_field = fix.MDEntrySize()
                if group.isSetField(size_field):
                    group.getField(size_field)
                    try:
                        size_val = float(size_field.getValue())
                    except ValueError:
                        size_val = 0.0

                entry = {"price": price_val, "size": size_val}

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
            import traceback
            print(f"[DEBUG] {traceback.format_exc()}")

    def processMarketDataIncremental(self, message):
        try:
            symbol = None
            no_entries = fix.NoMDEntries()
            message.getField(no_entries)
            count = no_entries.getValue()

            for i in range(1, count + 1):
                group = fix44.MarketDataIncrementalRefresh().NoMDEntries()
                message.getGroup(i, group)

                sym_field = fix.Symbol()
                md_update_action = fix.MDUpdateAction()
                entry_type = fix.MDEntryType()
                price = fix.MDEntryPx()
                size = fix.MDEntrySize()

                if group.isSetField(sym_field):
                    group.getField(sym_field)
                    symbol = sym_field.getValue()

                if not symbol:
                    continue  # пропуск, если нет символа

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

                if action == '0':
                    if not any(e["price"] == price_val for e in target_list):
                        target_list.append({"price": price_val, "size": size_val})
                elif action == '1':
                    for entry in target_list:
                        if entry["price"] == price_val:
                            entry["size"] = size_val
                            break
                elif action == '2':
                    target_list[:] = [entry for entry in target_list if entry["price"] != price_val]

            if symbol:
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
            no_related_sym = fix.NoRelatedSym()
            if message.isSetField(no_related_sym):
                message.getField(no_related_sym)
                count = no_related_sym.getValue()
                print(f"[DATA] SecurityList with {count} instruments")

                group = fix44.SecurityList.NoRelatedSym()
                for i in range(1, count + 1):
                    message.getGroup(i, group)
                    symbol = fix.Symbol()
                    if group.isSetField(symbol):
                        group.getField(symbol)
                        print(f"[DATA] Instrument: {symbol.getValue()}")
            else:
                print("[DATA] SecurityList received (empty or no symbols)")
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

        instruments = ["EUR/USD", "GBP/USD", "USD/CAD", "EUR/USD_ON", "GBP/USD_TN", "USD/CAD_TOM1W", "EUR/USD_2W"]

        Timer(0.1, lambda: self.send_security_definition_request("EUR/USD", True)).start()
        Timer(0.2, lambda: self.send_security_definition_request("GBP/USD", True)).start()

        for i, symbol in enumerate(instruments):
            try:
                delay = i * 0.3
                Timer(delay, lambda sym=symbol: self.send_market_data_request(sym)).start()
                print(f"[SEND] Scheduled subscription to {symbol} in {delay}s")
            except Exception as e:
                print(f"[ERROR] Scheduling subscription for {symbol}: {e}")

        Timer(6.0, lambda: self.send_quote_request("EUR/USD", 100000)).start()
        Timer(6.5, lambda: self.send_quote_request("EUR/USD_1W", 100000)).start()
        Timer(7.0, lambda: self.send_quote_request("EUR/USD_ON", 100000)).start()
        Timer(7.5, lambda: self.send_quote_request("GBP/USD_TN", 100000)).start()
        Timer(8.0, lambda: self.send_quote_request("USD/CAD_TOM1W", 100000)).start()

        Timer(8.5, lambda: self.send_quote_request("EUR/USD_OUT", 100000)).start()  # Broken date
        Timer(9.0, lambda: self.send_quote_request("EUR/USD_SWAP", 100000)).start()  # Broken dates

        Timer(9.5, lambda: self.send_quote_request("EUD/USK_SPOT", 100000)).start()

        Timer(10.0, lambda: self.send_quote_request("USD_OUT", 100000)).start()

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

    def send_security_definition_request(self, symbol, subscribe=True):
        try:
            msg = fix44.SecurityDefinitionRequest()
            msg.setField(fix.SecurityReqID(f"DEF_{symbol.replace('/', '')}"))
            msg.setField(fix.SecurityRequestType(1 if subscribe else 2))

            group = fix44.SecurityDefinitionRequest.NoRelatedSym()
            group.setField(fix.Symbol(symbol))
            msg.addGroup(group)

            fix.Session.sendToTarget(msg, self.session_id)
            print(f"[SEND] SecurityDefinitionRequest for {symbol}")
        except Exception as e:
            print(f"[ERROR] Sending SecurityDefinitionRequest: {e}")

    def send_market_data_unsubscribe(self, symbol):
        try:
            if symbol in self.market_data_subscriptions:
                req_id = self.market_data_subscriptions[symbol]
                msg = fix44.MarketDataRequest()
                msg.setField(fix.MDReqID(req_id))
                msg.setField(fix.SubscriptionRequestType('2'))
                msg.setField(fix.MarketDepth(0))
                msg.setField(fix.MDUpdateType(1))

                related_sym_group = fix44.MarketDataRequest.NoRelatedSym()
                related_sym_group.setField(fix.Symbol(symbol))
                msg.addGroup(related_sym_group)

                entry_types = ['0', '1']
                for et in entry_types:
                    md_entry_group = fix44.MarketDataRequest.NoMDEntryTypes()
                    md_entry_group.setField(fix.MDEntryType(et))
                    msg.addGroup(md_entry_group)

                fix.Session.sendToTarget(msg, self.session_id)
                del self.market_data_subscriptions[symbol]
                print(f"[SEND] Unsubscribed from {symbol}")
        except Exception as e:
            print(f"[ERROR] Unsubscribing from {symbol}: {e}")

    def send_quote_request(self, symbol, quantity):
        try:
            msg = fix44.QuoteRequest()
            msg.setField(fix.QuoteReqID(f"QR_{symbol.replace('/', '')}"))

            group = fix44.QuoteRequest.NoRelatedSym()
            group.setField(fix.Symbol(symbol))
            group.setField(fix.OrderQty(quantity))

            today = datetime.now()

            if "_ON" in symbol:
                sett_date = (today + timedelta(days=1)).strftime("%Y%m%d")
                group.setField(fix.FutSettDate(sett_date))

            elif "_TN" in symbol:
                sett_date = (today + timedelta(days=2)).strftime("%Y%m%d")
                group.setField(fix.FutSettDate(sett_date))

            elif "_TOM" in symbol:
                sett_date = (today + timedelta(days=1)).strftime("%Y%m%d")
                group.setField(fix.FutSettDate(sett_date))

            elif "_1W" in symbol:
                sett_date = (today + timedelta(days=7)).strftime("%Y%m%d")
                group.setField(fix.FutSettDate(sett_date))

            elif "_2W" in symbol:
                sett_date = (today + timedelta(days=14)).strftime("%Y%m%d")
                group.setField(fix.FutSettDate(sett_date))

            elif "_OUT" in symbol:
                sett_date = (today + timedelta(days=30)).strftime("%Y%m%d")
                group.setField(fix.FutSettDate(sett_date))

            msg.addGroup(group)

            fix.Session.sendToTarget(msg, self.session_id)
            print(f"[SEND] QuoteRequest for {symbol} {quantity}")

        except Exception as e:
            print(f"[ERROR] Sending QuoteRequest: {e}")

    def processQuote(self, message):
        try:
            quote_id = fix.QuoteID()
            symbol = fix.Symbol()
            message.getField(quote_id)
            message.getField(symbol)
            print(f"[QUOTE] Received for {symbol.getValue()}")
        except Exception as e:
            print(f"[ERROR] Processing quote: {e}")

    def processQuoteRequestReject(self, message):
        try:
            quote_req_id = fix.QuoteReqID()
            text = fix.Text()
            message.getField(quote_req_id)
            reject_text = text.getValue() if message.isSetField(text) else "No reason"
            print(f"[QUOTE REJECT] {quote_req_id.getValue()}: {reject_text}")
        except Exception as e:
            print(f"[ERROR] Processing quote reject: {e}")
import threading
from typing import Dict, Any, Optional

class ThreadSafeMarketData:
    def __init__(self):
        self._data: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def update(self, symbol: str, data: Dict[str, Any]) -> None:
        with self._lock:
            self._data[symbol] = data

    def get(self, symbol: str) -> Dict[str, Any]:
        with self._lock:
            data = self._data.get(symbol, {})
            if data:
                return {
                    'symbol': data.get('symbol', ''),
                    'timestamp': data.get('timestamp', ''),
                    'bids': data.get('bids', [])[:],
                    'asks': data.get('asks', [])[:],
                    'last_update': data.get('last_update', '')
                }
            return {}

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            result = {}
            for symbol, data in self._data.items():
                result[symbol] = {
                    'symbol': data.get('symbol', ''),
                    'timestamp': data.get('timestamp', ''),
                    'bids': data.get('bids', [])[:],
                    'asks': data.get('asks', [])[:],
                    'last_update': data.get('last_update', '')
                }
            return result

    def keys(self):
        with self._lock:
            return list(self._data.keys())

    def clear(self):
        with self._lock:
            self._data.clear()

market_data_store = ThreadSafeMarketData()
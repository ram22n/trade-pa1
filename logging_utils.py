# logging_utils.py
import csv, os, math
from datetime import datetime, timezone

CSV_HEADERS = [
    "ts_utc","version","run_id","order_id","client_order_id",
    "symbol","side","status","type","time_in_force",
    "submitted_qty","filled_qty","filled_avg_price","notional",
    "limit_price","stop_price","reason",
    "realized_pnl","position_after_close"
]

class TradeLogger:
    """
    Logs *actual fills* (not intentions) and computes realized P&L on SELL via FIFO.
    Maintains an in-process inventory per symbol for the session.
    """
    def __init__(self, csv_path: str, version="v2", run_id=None):
        self.path = csv_path
        self.version = version
        self.run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self._open_writer()
        self._lots = {}  # symbol -> list of [qty, price]

    def _open_writer(self):
        new_file = not os.path.exists(self.path)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._f = open(self.path, "a", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._f, fieldnames=CSV_HEADERS)
        if new_file:
            self._writer.writeheader()
            self._f.flush()

    def close(self):
        try:
            self._f.close()
        except Exception:
            pass

    def seed_position(self, symbol: str, qty: float, avg_price: float):
        """Seed FIFO lots for positions that already exist before this bot starts."""
        if qty > 0 and avg_price > 0:
            self._lots.setdefault(symbol, []).append([float(qty), float(avg_price)])

    def _fifo_realized(self, symbol: str, side: str, filled_qty: float, price: float) -> float:
        lots = self._lots.setdefault(symbol, [])
        realized = 0.0
        qty = float(filled_qty)

        if side.upper() == "BUY":
            lots.append([qty, float(price)])
            return 0.0

        # SELL: consume lots FIFO
        remaining = qty
        while remaining > 0 and lots:
            lot_qty, lot_price = lots[0]
            take = min(remaining, lot_qty)
            realized += (float(price) - lot_price) * take
            lot_qty -= take
            remaining -= take
            if lot_qty <= 1e-9:
                lots.pop(0)
            else:
                lots[0][0] = lot_qty
        return round(realized, 2)

    def log_fill(self, order, reason=""):
        """
        order: alpaca_trade_api.entity.Order (from REST.get_order*).
        Writes a row using filled facts. Computes realized P&L on SELL.
        """
        # Normalize strings to numbers where possible
        filled_qty = float(order.filled_qty or 0)
        filled_price = float(order.filled_avg_price or 0)
        notional = getattr(order, "notional", None)
        notional = float(notional) if notional not in (None, "") else ""

        realized_pnl = ""
        position_after = ""

        if filled_qty > 0 and filled_price > 0:
            if order.side.lower() == "buy":
                _ = self._fifo_realized(order.symbol, "BUY", filled_qty, filled_price)
            elif order.side.lower() == "sell":
                realized_pnl = self._fifo_realized(order.symbol, "SELL", filled_qty, filled_price)
                position_after = sum(q for q, _ in self._lots.get(order.symbol, []))

        row = {
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "version": self.version,
            "run_id": self.run_id,
            "order_id": order.id,
            "client_order_id": order.client_order_id,
            "symbol": order.symbol,
            "side": order.side.upper(),
            "status": order.status,
            "type": order.type,
            "time_in_force": order.time_in_force,
            "submitted_qty": order.qty or "",
            "filled_qty": filled_qty or "",
            "filled_avg_price": filled_price or "",
            "notional": notional,
            "limit_price": order.limit_price or "",
            "stop_price": order.stop_price or "",
            "reason": reason,
            "realized_pnl": realized_pnl,
            "position_after_close": position_after,
        }
        self._writer.writerow(row)
        self._f.flush()

//+------------------------------------------------------------------+
//|                                    TradeEdgeAutoJournal.mq5       |
//|  Watches your OWN real trades on this account and automatically   |
//|  creates/updates the matching journal entry on your TradeEdge     |
//|  website the moment you open a position, and again the moment     |
//|  you close it -- no manual "Save trade" needed for the basic      |
//|  facts (pair, direction, entry, SL, TP, lots, exit, P&L, exit      |
//|  reason). You still add the qualitative side yourself afterward    |
//|  (rules followed, worked/failed tags, emotion, notes) by editing   |
//|  the auto-created entry in the website's Journal tab.              |
//|                                                                    |
//|  ONE-TIME SETUP:                                                   |
//|  1. In MT5: Tools -> Options -> Expert Advisors -> check "Allow    |
//|     WebRequest for listed URL", then add your Render backend's     |
//|     URL (no trailing slash) -- the SAME one used for               |
//|     TradeEdgeLiveFeed.mq5, e.g.:                                    |
//|         https://tradeedge-backend-zeys.onrender.com                |
//|  2. Attach this EA to ANY ONE chart (it watches your whole account,|
//|     not just that chart's symbol) -- e.g. your main trading chart. |
//|     Only run ONE copy of this EA at a time; running it on multiple |
//|     charts simultaneously would push the same trade more than      |
//|     once.                                                          |
//|  3. On the website, go to AI Insights -> "Import trades from AI    |
//|     backend" (below "Sync my trades to AI backend") and click      |
//|     "Check for new trades" any time, or turn on its auto-check.    |
//|                                                                    |
//|  This EA never places, modifies, or closes any trade -- it only    |
//|  reports on trades YOU already opened/closed by whatever means     |
//|  (manually, another EA, mobile app, etc).                          |
//+------------------------------------------------------------------+
#property copyright "TradeEdge AI"
#property version   "1.00"
#property strict

input string BackendUrl = "https://your-app.onrender.com"; // Your Render backend URL (no trailing slash) -- same as TradeEdgeLiveFeed

// Poor-man's map: parallel arrays tracking each currently-open position's
// entry price / stop loss / direction, keyed by position ID, so that
// when the position closes we can still compute a realized R-multiple
// even though the closing deal itself doesn't carry the original SL.
long   g_posIds[];
double g_posEntries[];
double g_posSLs[];
int    g_posDirections[]; // +1 = buy, -1 = sell

//+------------------------------------------------------------------+
int OnInit()
{
   Print("TradeEdge Auto-Journal: watching this account for trade open/close events. ",
         "Run only ONE copy of this EA across all your charts.");
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
int FindPositionIndex(long positionId)
{
   for(int i = 0; i < ArraySize(g_posIds); i++)
      if(g_posIds[i] == positionId)
         return i;
   return -1;
}

void TrackPositionOpen(long positionId, double entry, double sl, int direction)
{
   int idx = FindPositionIndex(positionId);
   if(idx < 0)
   {
      int n = ArraySize(g_posIds);
      ArrayResize(g_posIds, n + 1);
      ArrayResize(g_posEntries, n + 1);
      ArrayResize(g_posSLs, n + 1);
      ArrayResize(g_posDirections, n + 1);
      idx = n;
   }
   g_posIds[idx] = positionId;
   g_posEntries[idx] = entry;
   g_posSLs[idx] = sl;
   g_posDirections[idx] = direction;
}

void UntrackPosition(long positionId)
{
   int idx = FindPositionIndex(positionId);
   if(idx < 0) return;
   int last = ArraySize(g_posIds) - 1;
   g_posIds[idx] = g_posIds[last];
   g_posEntries[idx] = g_posEntries[last];
   g_posSLs[idx] = g_posSLs[last];
   g_posDirections[idx] = g_posDirections[last];
   ArrayResize(g_posIds, last);
   ArrayResize(g_posEntries, last);
   ArrayResize(g_posSLs, last);
   ArrayResize(g_posDirections, last);
}

//+------------------------------------------------------------------+
//| Very rough asset-class guess from the symbol name -- a convenience|
//| default the user can always correct in the website's Journal tab. |
//+------------------------------------------------------------------+
string GuessAsset(string sym)
{
   string s = sym;
   StringToUpper(s);
   if(StringFind(s, "XAU") >= 0 || StringFind(s, "GOLD") >= 0 || StringFind(s, "XAG") >= 0 || StringFind(s, "SILVER") >= 0)
      return "Metals";
   if(StringFind(s, "BTC") >= 0 || StringFind(s, "ETH") >= 0 || StringFind(s, "CRYPTO") >= 0)
      return "Crypto";
   if(StringFind(s, "CASH") >= 0 || StringFind(s, "US30") >= 0 || StringFind(s, "US100") >= 0 ||
      StringFind(s, "GER40") >= 0 || StringFind(s, "UK100") >= 0 || StringFind(s, "NAS") >= 0 ||
      StringFind(s, "SPX") >= 0 || StringFind(s, "DOW") >= 0)
      return "Indices";
   if(StringFind(s, "OIL") >= 0 || StringFind(s, "WTI") >= 0 || StringFind(s, "BRENT") >= 0)
      return "Commodities";
   return "Forex";
}

//+------------------------------------------------------------------+
string YyyyMmDd(datetime t)
{
   string s = TimeToString(t, TIME_DATE);
   StringReplace(s, ".", "-");
   return s;
}

//+------------------------------------------------------------------+
//| Maps MT5's own close reason to a human exit reason string, so the |
//| journal is pre-filled with something useful instead of "Unknown". |
//+------------------------------------------------------------------+
string ExitReasonFromDealReason(long reason)
{
   switch((int)reason)
   {
      case DEAL_REASON_SL:     return "Stop Loss Hit";
      case DEAL_REASON_TP:     return "Take Profit Hit";
      case DEAL_REASON_SO:     return "Stop Out (margin)";
      case DEAL_REASON_CLIENT: return "Manual Close";
      case DEAL_REASON_MOBILE: return "Manual Close (mobile)";
      case DEAL_REASON_WEB:    return "Manual Close (web)";
      case DEAL_REASON_EXPERT: return "Closed by EA";
      default:                 return "Other";
   }
}

//+------------------------------------------------------------------+
//| POSTs one JSON body to /api/v1/trades -- upsert semantics: the     |
//| open event and the close event use the SAME id, and only the      |
//| fields present in each payload get written, so the close event's   |
//| smaller payload never blanks out what the open event already set. |
//+------------------------------------------------------------------+
void PostTrade(string bodyJson, string label)
{
   char postData[];
   int dataLen = StringToCharArray(bodyJson, postData) - 1;
   ArrayResize(postData, dataLen);

   char result[];
   string resultHeaders;
   string headers = "Content-Type: application/json\r\n";
   string url = BackendUrl + "/api/v1/trades";

   ResetLastError();
   int status = WebRequest("POST", url, headers, 5000, postData, result, resultHeaders);

   if(status == -1)
   {
      int err = GetLastError();
      Print("TradeEdge Auto-Journal: WebRequest failed (", label, "), error ", err,
            ". Check Tools -> Options -> Expert Advisors -> 'Allow WebRequest for listed URL' includes: ", BackendUrl);
      return;
   }
   Print("TradeEdge Auto-Journal: ", label, " -> HTTP ", status, ". Response: ", CharArrayToString(result));
}

//+------------------------------------------------------------------+
void HandlePositionOpen(ulong dealTicket, long positionId, string symbol)
{
   long dealType = HistoryDealGetInteger(dealTicket, DEAL_TYPE);
   int direction = (dealType == DEAL_TYPE_BUY) ? 1 : -1;
   double entry = HistoryDealGetDouble(dealTicket, DEAL_PRICE);
   double volume = HistoryDealGetDouble(dealTicket, DEAL_VOLUME);
   datetime openTime = (datetime)HistoryDealGetInteger(dealTicket, DEAL_TIME);

   double sl = 0, tp = 0;
   if(PositionSelectByTicket(positionId))
   {
      sl = PositionGetDouble(POSITION_SL);
      tp = PositionGetDouble(POSITION_TP);
   }

   TrackPositionOpen(positionId, entry, sl, direction);

   long account = AccountInfoInteger(ACCOUNT_LOGIN);
   string id = "mt5-" + IntegerToString(account) + "-" + IntegerToString(positionId);

   string body = "{";
   body += "\"id\":\"" + id + "\",";
   body += "\"date\":\"" + YyyyMmDd(openTime) + "\",";
   body += "\"pair\":\"" + symbol + "\",";
   body += "\"direction\":\"" + (direction > 0 ? "buy" : "sell") + "\",";
   body += "\"asset\":\"" + GuessAsset(symbol) + "\",";
   body += "\"entry\":" + DoubleToString(entry, _Digits) + ",";
   if(sl > 0) body += "\"sl\":" + DoubleToString(sl, _Digits) + ",";
   if(tp > 0) body += "\"tp\":" + DoubleToString(tp, _Digits) + ",";
   body += "\"lots\":" + DoubleToString(volume, 2);
   body += "}";

   PostTrade(body, "opened " + symbol + " " + (direction > 0 ? "buy" : "sell"));
}

//+------------------------------------------------------------------+
void HandlePositionClose(ulong dealTicket, long positionId, string symbol)
{
   double exitPrice = HistoryDealGetDouble(dealTicket, DEAL_PRICE);
   double profit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT)
                 + HistoryDealGetDouble(dealTicket, DEAL_SWAP)
                 + HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);
   long reason = HistoryDealGetInteger(dealTicket, DEAL_REASON);

   // The website's Exit Reason dropdown has specific, subjective manual-
   // close categories (Target Reached / Fear / New POI / Structure Break
   // / News) that MT5 has no way to know -- only fill this in when we're
   // objectively certain (the broker itself closed it via SL or TP);
   // otherwise leave it blank so the dropdown shows "-- Select --" and
   // the user picks the real reason themselves, rather than silently
   // writing a generic "Manual Close" that won't match any option.
   bool haveExitReason = (reason == DEAL_REASON_SL || reason == DEAL_REASON_TP);
   string exitReason = haveExitReason ? ExitReasonFromDealReason(reason) : "";

   long account = AccountInfoInteger(ACCOUNT_LOGIN);
   string id = "mt5-" + IntegerToString(account) + "-" + IntegerToString(positionId);

   // Realized R-multiple, only if we saw this position's own open event
   // in this same EA session and it had a stop loss set.
   double rr = 0;
   bool haveRr = false;
   int idx = FindPositionIndex(positionId);
   if(idx >= 0 && g_posSLs[idx] > 0)
   {
      double risk = MathAbs(g_posEntries[idx] - g_posSLs[idx]);
      double reward = MathAbs(exitPrice - g_posEntries[idx]);
      if(risk > 0)
      {
         rr = reward / risk;
         haveRr = true;
      }
   }

   string body = "{";
   body += "\"id\":\"" + id + "\",";
   body += "\"exit\":" + DoubleToString(exitPrice, _Digits) + ",";
   body += "\"pnl\":" + DoubleToString(profit, 2);
   if(haveRr) body += ",\"rr\":" + DoubleToString(rr, 2);
   if(haveExitReason) body += ",\"exitReason\":\"" + exitReason + "\"";
   body += "}";

   PostTrade(body, "closed " + symbol + (haveExitReason ? " (" + exitReason + ")" : " (manual/other -- pick exit reason on the website)"));
   UntrackPosition(positionId);
}

//+------------------------------------------------------------------+
//| Fires on every trade-related event on this account. We only act on|
//| TRADE_TRANSACTION_DEAL_ADD -- a new deal landing in history is the |
//| one event guaranteed to fire exactly once per open and once per    |
//| close, regardless of whether it came from this terminal, mobile,   |
//| another EA, or a partial close.                                    |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result)
{
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD)
      return;

   ulong dealTicket = trans.deal;
   if(!HistoryDealSelect(dealTicket))
      return;

   string symbol = HistoryDealGetString(dealTicket, DEAL_SYMBOL);
   if(symbol == "")
      return; // balance/credit/other non-trade deals have no symbol

   long positionId = (long)HistoryDealGetInteger(dealTicket, DEAL_POSITION_ID);
   long entryType = HistoryDealGetInteger(dealTicket, DEAL_ENTRY);

   if(entryType == DEAL_ENTRY_IN)
      HandlePositionOpen(dealTicket, positionId, symbol);
   else if(entryType == DEAL_ENTRY_OUT || entryType == DEAL_ENTRY_OUT_BY)
      HandlePositionClose(dealTicket, positionId, symbol);
}
//+------------------------------------------------------------------+

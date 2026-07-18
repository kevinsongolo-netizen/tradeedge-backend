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
   // Rebuild the entry/SL tracking table from whatever positions are
   // CURRENTLY open, so that R:R still computes correctly for a trade
   // that was opened before this EA was (re)attached or recompiled --
   // otherwise the in-memory arrays below start empty on every restart
   // and any position opened in a previous run closes with no R:R.
   //
   // Sprint 20 fix -- this used to ONLY track locally. OnTradeTransaction
   // fires for NEW deals from this point forward only, so a position that
   // was already open before the EA (re)started would be tracked here for
   // R:R math but would NEVER actually reach the website's Journal -- its
   // original "open" event already happened before this run began, and
   // nothing retroactively reports it. Now each currently-open position is
   // also (re)posted to the backend below; that's always safe even if it
   // was already reported in a previous run, since /api/v1/trades upserts
   // by id (same "mt5-<account>-<positionId>" id every time).
   int rebuilt = 0;
   for(int i = 0; i < PositionsTotal(); i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;

      long posId = (long)PositionGetInteger(POSITION_IDENTIFIER);
      string symbol = PositionGetString(POSITION_SYMBOL);
      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl = PositionGetDouble(POSITION_SL);
      double tp = PositionGetDouble(POSITION_TP);
      double volume = PositionGetDouble(POSITION_VOLUME);
      datetime openTime = (datetime)PositionGetInteger(POSITION_TIME);
      int direction = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;

      TrackPositionOpen(posId, entry, sl, direction);

      string body = BuildOpenBody(posId, symbol, direction, entry, sl, tp, volume, openTime);
      PostTrade(body, "restored open " + symbol + " " + (direction > 0 ? "buy" : "sell"));
      rebuilt++;
   }

   Print("TradeEdge Auto-Journal: watching this account for trade open/close events. ",
         "Restored + reported ", rebuilt, " currently-open position(s) to the website. ",
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
//| Same session buckets as the website's own sessionFromHour() JS    |
//| helper (used for its CSV/Excel import) -- kept identical so a     |
//| trade auto-filled by this EA matches what manual import would've  |
//| picked. Uses the trade's open hour in your BROKER'S SERVER time,  |
//| same as that existing feature -- if your broker's server timezone |
//| doesn't line up with these windows, just correct it on the site.  |
//+------------------------------------------------------------------+
string SessionFromHour(int hour)
{
   if(hour >= 0 && hour < 7)  return "Asian";
   if(hour >= 7 && hour < 12) return "London";
   if(hour >= 12 && hour < 16) return "London/NY Overlap";
   if(hour >= 16 && hour < 21) return "New York";
   return "Asian";
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
// Shared by HandlePositionOpen (a brand-new deal, from OnTradeTransaction)
// and OnInit's rebuild loop (a position that was already open when the EA
// started) -- both know entry/SL/TP/direction/volume/openTime/symbol
// already, just from different sources (a history deal vs. the live
// position), so there's no need for two separate JSON builders.
string BuildOpenBody(long positionId, string symbol, int direction, double entry, double sl, double tp, double volume, datetime openTime)
{
   long account = AccountInfoInteger(ACCOUNT_LOGIN);
   string id = "mt5-" + IntegerToString(account) + "-" + IntegerToString(positionId);

   // Use the DIGITS of the symbol actually being traded, not _Digits
   // (which is the digits of whatever chart this EA happens to be
   // attached to). This EA tracks trades across every symbol, so
   // formatting with the chart's own digits would wrongly truncate
   // prices for any other symbol (e.g. a 2-digit index chart would
   // round forex entries like 0.81340 down to 0.81).
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);

   MqlDateTime tm;
   TimeToStruct(openTime, tm);
   string session = SessionFromHour(tm.hour);

   string body = "{";
   body += "\"id\":\"" + id + "\",";
   body += "\"date\":\"" + YyyyMmDd(openTime) + "\",";
   body += "\"pair\":\"" + symbol + "\",";
   body += "\"direction\":\"" + (direction > 0 ? "buy" : "sell") + "\",";
   body += "\"asset\":\"" + GuessAsset(symbol) + "\",";
   body += "\"session\":\"" + session + "\",";
   body += "\"entry\":" + DoubleToString(entry, digits) + ",";
   if(sl > 0) body += "\"sl\":" + DoubleToString(sl, digits) + ",";
   if(tp > 0) body += "\"tp\":" + DoubleToString(tp, digits) + ",";
   body += "\"lots\":" + DoubleToString(volume, 2);
   body += "}";
   return body;
}

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
   string body = BuildOpenBody(positionId, symbol, direction, entry, sl, tp, volume, openTime);
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

   // Same reasoning as HandlePositionOpen: use the traded symbol's own
   // digits, not the attached chart's _Digits.
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);

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
   body += "\"exit\":" + DoubleToString(exitPrice, digits) + ",";
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

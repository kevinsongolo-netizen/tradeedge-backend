//+------------------------------------------------------------------+
//|                                        TradeEdgeLiveFeed.mq5      |
//|  Pushes the current price for this chart's symbol to your        |
//|  TradeEdge AI backend, so the website's Live Opportunity Scanner  |
//|  can compare it against your own screenshot-logged open trades'   |
//|  SL/TP and flag anything that needs attention. Also pushes your   |
//|  account balance/equity/margin each tick (Sprint 18) so the       |
//|  website can show a margin-call/stop-out buffer warning, and      |
//|  sends a free MT5 mobile push notification the moment that        |
//|  margin status goes to WARNING or DANGER, so you don't have to    |
//|  keep the website open to find out.                                |
//|                                                                    |
//|  Sprint 20 -- the old rule engine (Smart Money Concepts checks,   |
//|  VALID/INVALID verdicts, phone alerts on a new VALID setup) was    |
//|  retired along with the strategy engine it depended on. This EA   |
//|  no longer sends candle history or reads a trade verdict back --  |
//|  it just pushes price. Reviewing setups now happens from your own |
//|  screenshots on the website (Pre-Trade Check / Chart Analysis     |
//|  Engine), and watching an already-logged open trade against live  |
//|  price happens on the website's Live Opportunity Scanner card.    |
//|                                                                    |
//|  ONE-TIME SETUP:                                                   |
//|  1. In MT5: Tools -> Options -> Expert Advisors -> check "Allow    |
//|     WebRequest for listed URL", then add your Render backend's    |
//|     URL (no trailing slash), e.g.:                                 |
//|         https://tradeedge-backend-zeys.onrender.com                |
//|  2. (Optional, for phone alerts) Tools -> Options -> Notifications |
//|     -> check "Enable Push Notifications", then open the MT5       |
//|     mobile app on your phone, go to Settings -> Messages, and      |
//|     copy the MetaQuotes ID shown there back into the desktop       |
//|     terminal's Notifications tab.                                  |
//|  3. Drag this EA onto the chart of the symbol you want to feed     |
//|     (e.g. an XAUUSD chart -- any timeframe, it only reads price).  |
//|     Fill in the Inputs below (right-click chart -> Expert Advisors |
//|     -> Properties -> Inputs). The Timeframe Label just needs to    |
//|     match whatever label your logged trades' pair convention uses |
//|     -- it's stored alongside the price but no longer drives any    |
//|     rule logic.                                                    |
//|                                                                    |
//|  This EA only pushes price and account info out — it never places |
//|  trades or changes anything in your account.                      |
//+------------------------------------------------------------------+
#property copyright "TradeEdge AI"
#property version   "2.00"
#property strict

input string BackendUrl          = "https://your-app.onrender.com"; // Your Render backend URL (no trailing slash)
input string SymbolOverride      = "";     // Leave blank to use this chart's own symbol
input string TimeframeLabel      = "M15";  // Label sent to the backend alongside the price
input int    PushIntervalSeconds = 30;     // How often to push fresh price to the backend
input bool   PushMarginBuffer     = true;   // Also push account balance/equity/margin each tick (Sprint 18)
input bool   PushMarginAlerts      = true;  // Send a phone push notification when margin buffer status is WARNING or DANGER
input int    MarginRepeatAlertMinutes = 15; // Don't repeat the same margin WARNING/DANGER alert more often than this

datetime lastMarginNotifyTime = 0;
string   lastMarginNotifyStatus = "";

//+------------------------------------------------------------------+
int OnInit()
{
   EventSetTimer(PushIntervalSeconds);
   PushLiveData(); // push once immediately so the website has data right away
   if(PushMarginBuffer)
      PushAccountMargin();
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   PushLiveData();
   if(PushMarginBuffer)
      PushAccountMargin();
}

//+------------------------------------------------------------------+
//| Extracts VALUE from a "KEY=VALUE" line in the plain-text response |
//+------------------------------------------------------------------+
string ExtractValue(string text, string key)
{
   string marker = key + "=";
   int pos = StringFind(text, marker);
   if(pos < 0)
      return "";
   int start = pos + StringLen(marker);
   int end = StringFind(text, "\n", start);
   if(end < 0)
      end = StringLen(text);
   return StringSubstr(text, start, end - start);
}

//+------------------------------------------------------------------+
//| Builds the request body and POSTs the current price to the        |
//| backend. Sprint 20 -- no more candle history, no more rule flags; |
//| the backend just records price now (see app/api/v1/live.py).      |
//+------------------------------------------------------------------+
void PushLiveData()
{
   string sym = (SymbolOverride == "") ? _Symbol : SymbolOverride;

   double bid = SymbolInfoDouble(sym, SYMBOL_BID);
   double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
   double price = (bid > 0 && ask > 0) ? (bid + ask) / 2.0 : bid;

   if(bid <= 0 && ask <= 0)
   {
      Print("TradeEdge Live Feed: no price available yet for ", sym, " -- skipping this push.");
      return;
   }

   string body = "{";
   body += "\"symbol\":\"" + sym + "\",";
   body += "\"timeframe\":\"" + TimeframeLabel + "\",";
   body += "\"price\":" + DoubleToString(price, _Digits) + ",";
   body += "\"bid\":" + DoubleToString(bid, _Digits) + ",";
   body += "\"ask\":" + DoubleToString(ask, _Digits);
   body += "}";

   char postData[];
   int dataLen = StringToCharArray(body, postData) - 1; // exclude the trailing null terminator
   ArrayResize(postData, dataLen);

   char result[];
   string resultHeaders;
   string headers = "Content-Type: application/json\r\n";
   string url = BackendUrl + "/api/v1/live/ingest?format=plain";

   ResetLastError();
   int status = WebRequest("POST", url, headers, 5000, postData, result, resultHeaders);

   if(status == -1)
   {
      int err = GetLastError();
      Print("TradeEdge Live Feed: WebRequest failed, error ", err,
            ". Check Tools -> Options -> Expert Advisors -> 'Allow WebRequest for listed URL' includes: ", BackendUrl);
      return;
   }

   string response = CharArrayToString(result);
   Print("TradeEdge Live Feed: pushed price for ", sym, " ", TimeframeLabel,
         " (HTTP ", status, "). Response: ", response);
   // Sprint 20 -- the response is now just an echo of what was ingested
   // (SYMBOL/TIMEFRAME/PRICE/BID/ASK), not a rule-engine verdict, so
   // there's nothing left to alert on here. Reviewing a setup happens
   // from your own screenshots on the website; watching an already-
   // logged open trade against this price happens on the website's
   // Live Opportunity Scanner card.
}
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
//| Sprint 18 -- pushes raw account balance/equity/margin so the      |
//| website can show a margin-call/stop-out buffer warning. This EA   |
//| never places trades or changes account settings -- it only reads  |
//| account info and posts it, same as the price push above.          |
//+------------------------------------------------------------------+
void PushAccountMargin()
{
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity  = AccountInfoDouble(ACCOUNT_EQUITY);
   double margin  = AccountInfoDouble(ACCOUNT_MARGIN);

   string body = "{";
   body += "\"balance\":" + DoubleToString(balance, 2) + ",";
   body += "\"equity\":" + DoubleToString(equity, 2) + ",";
   body += "\"margin\":" + DoubleToString(margin, 2);
   body += "}";

   char postData[];
   int dataLen = StringToCharArray(body, postData) - 1;
   ArrayResize(postData, dataLen);

   char result[];
   string resultHeaders;
   string headers = "Content-Type: application/json\r\n";
   string url = BackendUrl + "/api/v1/account-margin/ingest?format=plain";

   ResetLastError();
   int status = WebRequest("POST", url, headers, 5000, postData, result, resultHeaders);

   if(status == -1)
   {
      int err = GetLastError();
      Print("TradeEdge Live Feed: margin push failed, error ", err,
            ". Check Tools -> Options -> Expert Advisors -> 'Allow WebRequest for listed URL' includes: ", BackendUrl);
      return;
   }

   string response = CharArrayToString(result);
   string status_ = ExtractValue(response, "STATUS");
   Print("TradeEdge Live Feed: margin push OK (HTTP ", status, "), status=", status_, ". Response: ", response);
   if(status_ == "DANGER")
      Print("TradeEdge Live Feed: MARGIN BUFFER DANGER -- ", response);

   HandleMarginPlainResponse(response);
}

//+------------------------------------------------------------------+
//| Sends a phone push notification when the margin buffer status is  |
//| WARNING or DANGER, not more than once per MarginRepeatAlertMinutes|
//| for the same status. This is the real safety net if you're not    |
//| using a fixed stop loss on a given trade -- it only WARNS, it      |
//| never closes anything itself.                                     |
//+------------------------------------------------------------------+
void HandleMarginPlainResponse(string response)
{
   if(!PushMarginAlerts)
      return;

   string status_ = ExtractValue(response, "STATUS");
   if(status_ != "WARNING" && status_ != "DANGER")
   {
      lastMarginNotifyStatus = status_;
      return;
   }

   string marginPct  = ExtractValue(response, "MARGIN_LEVEL_PCT");
   string bufferCall = ExtractValue(response, "BUFFER_TO_MARGIN_CALL_PCT");

   datetime now = TimeCurrent();
   bool statusChanged   = (status_ != lastMarginNotifyStatus);
   bool cooldownElapsed = ((int)(now - lastMarginNotifyTime) >= MarginRepeatAlertMinutes * 60);
   if(statusChanged || cooldownElapsed)
   {
      string msg = "TradeEdge Margin " + status_ + ": level " + marginPct +
                   "% (" + bufferCall + " pts above margin call). Check your account.";
      SendNotification(msg);
      Print("TradeEdge Live Feed: sent MARGIN push notification -> ", msg);
      lastMarginNotifyTime = now;
   }
   lastMarginNotifyStatus = status_;
}

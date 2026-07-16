//+------------------------------------------------------------------+
//|                                        TradeEdgeLiveFeed.mq5      |
//|  Pushes recent candle data from this chart to your TradeEdge AI   |
//|  backend, and sends a free MT5 mobile push notification whenever  |
//|  the backend says a trade setup is VALID. Also pushes your account|
//|  balance/equity/margin each tick (Sprint 18) so the website can   |
//|  show a margin-call/stop-out buffer warning -- there is no fixed  |
//|  stop loss in the Personal Averaging Strategy, so this is the     |
//|  real safety net: it only WARNS, it never closes anything. Also   |
//|  sends its OWN phone push notification the moment margin status   |
//|  goes to WARNING or DANGER, so you don't have to keep the website |
//|  open to find out -- same free push mechanism as the VALID alert. |
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
//|  3. Drag this EA onto the chart of the symbol + timeframe you want |
//|     to feed (e.g. an EURUSD H4 chart). Fill in the Inputs below    |
//|     (right-click chart -> Expert Advisors -> Properties -> Inputs).|
//|  4. On your website's Chart Analysis Engine card, choose "Live     |
//|     feed (from MT5)" and type the EXACT same Symbol + Timeframe    |
//|     Label you set below.                                           |
//|                                                                    |
//|  This EA only pushes candle data out — it never places trades or   |
//|  changes anything in your account.                                 |
//+------------------------------------------------------------------+
#property copyright "TradeEdge AI"
#property version   "1.00"
#property strict

input string BackendUrl          = "https://your-app.onrender.com"; // Your Render backend URL (no trailing slash)
input string SymbolOverride      = "";     // Leave blank to use this chart's own symbol
input string TimeframeLabel      = "H4";   // Label sent to the backend -- must match what you type on the website
input int    CandleCount         = 60;     // How many recent candles to send each push
input bool   IncludeM15Confirmation = true; // Also send M15 candles for automatic multi-timeframe confirmation
input int    M15CandleCount      = 30;     // How many M15 candles to send (only used if the above is true)
input double MinRiskReward       = 2.0;    // Minimum R:R required for a VALID setup
input int    PushIntervalSeconds = 60;     // How often to push fresh data to the backend
input int    RepeatAlertMinutes  = 60;     // Don't repeat the same VALID phone alert more often than this
input bool   PushMarginBuffer     = true;   // Also push account balance/equity/margin each tick (Sprint 18)
input bool   IncludeDailyBias     = true;   // Also send Daily candles for the Personal Averaging Strategy's Daily Bias rule (Sprint 18)
input int    DailyCandleCount     = 10;     // How many D1 candles to send (only used if the above is true)
input bool   PushMarginAlerts      = true;  // Send a phone push notification when margin buffer status is WARNING or DANGER
input int    MarginRepeatAlertMinutes = 15; // Don't repeat the same margin WARNING/DANGER alert more often than this -- shorter than RepeatAlertMinutes since a margin problem is more urgent than a trade setup

datetime lastNotifyTime = 0;
string   lastNotifyStatus = "";
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
//| Builds a JSON array of candles: [{"time":...,"open":...,...}, ...]|
//+------------------------------------------------------------------+
string CandlesToJsonArray(string sym, ENUM_TIMEFRAMES tf, int count)
{
   MqlRates rates[];
   int copied = CopyRates(sym, tf, 0, count, rates);
   if(copied <= 0)
      return "[]";
   ArraySetAsSeries(rates, false); // oldest first, matching the website's own candle boxes

   string json = "[";
   for(int i = 0; i < copied; i++)
   {
      string t = TimeToString(rates[i].time, TIME_DATE | TIME_MINUTES);
      StringReplace(t, ".", "-");
      StringReplace(t, " ", "T");
      json += "{\"time\":\"" + t + "\",\"open\":" + DoubleToString(rates[i].open, _Digits) +
              ",\"high\":" + DoubleToString(rates[i].high, _Digits) +
              ",\"low\":" + DoubleToString(rates[i].low, _Digits) +
              ",\"close\":" + DoubleToString(rates[i].close, _Digits) + "}";
      if(i < copied - 1)
         json += ",";
   }
   json += "]";
   return json;
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
//| Sends a phone push notification if the backend says VALID, but   |
//| not more than once per RepeatAlertMinutes for the same status.    |
//+------------------------------------------------------------------+
void HandlePlainResponse(string response)
{
   string status = ExtractValue(response, "STATUS");
   string recommendation = ExtractValue(response, "RECOMMENDATION");
   string headline = ExtractValue(response, "HEADLINE");
   string direction = ExtractValue(response, "DIRECTION");
   string confidence = ExtractValue(response, "CONFIDENCE");

   if(status == "VALID")
   {
      datetime now = TimeCurrent();
      bool statusChanged = (status != lastNotifyStatus);
      bool cooldownElapsed = ((int)(now - lastNotifyTime) >= RepeatAlertMinutes * 60);
      if(statusChanged || cooldownElapsed)
      {
         string msg = TimeframeLabel + " " + _Symbol + ": " + headline +
                      " (" + recommendation + " " + direction + ", confidence " + confidence + "%)";
         SendNotification(msg);
         Print("TradeEdge Live Feed: sent push notification -> ", msg);
         lastNotifyTime = now;
      }
   }
   lastNotifyStatus = status;
}

//+------------------------------------------------------------------+
//| Sprint 18 -- true if there's an open position on ``sym`` (any      |
//| magic number, so it also catches manually-placed trades) that is   |
//| currently floating in a loss. Feeds rule 3's add-on entry check    |
//| automatically instead of needing a manual checkbox on the website. |
//+------------------------------------------------------------------+
bool HasOpenLosingPosition(string sym)
{
   int total = PositionsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(!PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) != sym)
         continue;
      if(PositionGetDouble(POSITION_PROFIT) < 0)
         return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Builds the request body and POSTs it to the backend               |
//+------------------------------------------------------------------+
void PushLiveData()
{
   string sym = (SymbolOverride == "") ? _Symbol : SymbolOverride;
   ENUM_TIMEFRAMES tf = Period();

   string candlesJson = CandlesToJsonArray(sym, tf, CandleCount);
   if(candlesJson == "[]")
   {
      Print("TradeEdge Live Feed: not enough candle history yet on this chart -- skipping this push.");
      return;
   }

   string body = "{";
   body += "\"symbol\":\"" + sym + "\",";
   body += "\"timeframe\":\"" + TimeframeLabel + "\",";
   body += "\"candles\":" + candlesJson + ",";
   if(IncludeM15Confirmation)
   {
      string m15Json = CandlesToJsonArray(sym, PERIOD_M15, M15CandleCount);
      if(m15Json != "[]")
         body += "\"m15Candles\":" + m15Json + ",";
   }
   if(IncludeDailyBias)
   {
      string dailyJson = CandlesToJsonArray(sym, PERIOD_D1, DailyCandleCount);
      if(dailyJson != "[]")
         body += "\"dailyCandles\":" + dailyJson + ",";
   }
   body += "\"openTradeInLoss\":" + (HasOpenLosingPosition(sym) ? "true" : "false") + ",";
   body += "\"minRr\":" + DoubleToString(MinRiskReward, 2);
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
   Print("TradeEdge Live Feed: pushed ", CandleCount, " candles for ", sym, " ", TimeframeLabel,
         " (HTTP ", status, "). Response: ", response);

   HandlePlainResponse(response);
}
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
//| Sprint 18 -- pushes raw account balance/equity/margin so the      |
//| website can show a margin-call/stop-out buffer warning. This EA   |
//| never places trades or changes account settings -- it only reads  |
//| account info and posts it, same as the candle push above.         |
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
//| for the same status. This is the real safety net for the Personal |
//| Averaging Strategy's no-fixed-stop-loss design -- it only WARNS,  |
//| it never closes anything itself.                                  |
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
                   "% (" + bufferCall + " pts above margin call). No fixed stop loss is set -- check your account.";
      SendNotification(msg);
      Print("TradeEdge Live Feed: sent MARGIN push notification -> ", msg);
      lastMarginNotifyTime = now;
   }
   lastMarginNotifyStatus = status_;
}

//+------------------------------------------------------------------+
//|                                        TradeEdgeLiveFeed.mq5      |
//|  Pushes recent candle data from this chart to your TradeEdge AI   |
//|  backend, and sends a free MT5 mobile push notification whenever  |
//|  the backend says a trade setup is VALID.                         |
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

datetime lastNotifyTime = 0;
string   lastNotifyStatus = "";

//+------------------------------------------------------------------+
int OnInit()
{
   EventSetTimer(PushIntervalSeconds);
   PushLiveData(); // push once immediately so the website has data right away
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   PushLiveData();
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

from fastapi import FastAPI, Request, HTTPException
import uvicorn
import yfinance as yf
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Stock Fundamentals Webhook")

@app.get("/")
async def root():
    return {"message": "Stock Fundamentals Webhook is active"}

@app.post("/webhook/fundamentals")
async def get_fundamentals(request: Request):
    try:
        data = await request.json()
        # Accept 'ticker' or 'symbol'
        ticker_symbol = data.get("ticker") or data.get("symbol")
        
        if not ticker_symbol:
            raise HTTPException(status_code=400, detail="Ticker symbol is required (use 'ticker' or 'symbol' key)")
        
        logger.info(f"Fetching data for: {ticker_symbol}")
        stock = yf.Ticker(ticker_symbol)
        info = stock.info
        
        if not info or len(info) < 5: # Basic check to see if we got valid data
            raise HTTPException(status_code=404, detail=f"Ticker '{ticker_symbol}' not found or no data available")

        # Get financial statements for complex calculations
        financials = stock.financials
        balance_sheet = stock.balance_sheet
        cashflow = stock.cash_flow
        history_5y = stock.history(period="5y")

        def calculate_roic():
            try:
                # ROIC = NOPAT / Invested Capital
                # NOPAT = EBIT * (1 - Tax Rate)
                ebit = financials.loc['EBIT'].iloc[0]
                tax_provision = financials.loc['Tax Provision'].iloc[0]
                pretax_income = financials.loc['Pretax Income'].iloc[0]
                tax_rate = tax_provision / pretax_income if pretax_income > 0 else 0.25
                nopat = ebit * (1 - tax_rate)
                
                # Invested Capital = Total Debt + Total Equity
                total_debt = info.get("totalDebt", 0) or 0
                total_equity = info.get("totalStockholderEquity") or balance_sheet.loc['Stockholders Equity'].iloc[0]
                invested_capital = total_debt + total_equity
                return nopat / invested_capital if invested_capital > 0 else None
            except: return None

        def calculate_revenue_cagr_5y():
            try:
                revs = financials.loc['Total Revenue']
                if len(revs) >= 4: # yfinance usually provides 4 years of annual data
                    end_rev = revs.iloc[0]
                    start_rev = revs.iloc[-1]
                    years = len(revs) - 1
                    return (end_rev / start_rev) ** (1/years) - 1
                return None
            except: return None

        def calculate_shareholder_yield():
            try:
                # (Dividends Paid + Share Repurchases) / Market Cap
                div_yield = info.get("dividendYield", 0) or 0
                repurchases = abs(cashflow.loc['Repurchase Of Capital Stock'].iloc[0]) if 'Repurchase Of Capital Stock' in cashflow.index else 0
                market_cap = info.get("marketCap")
                buyback_yield = repurchases / market_cap if market_cap else 0
                return div_yield + buyback_yield
            except: return None

        # Extract and calculate requested metrics
        metrics = {
            "symbol": info.get("symbol"),
            "longName": info.get("longName"),
            
            # Requested Fundamentals
            "marketCap": info.get("marketCap"),
            "peRatio": info.get("trailingPE"),
            "pegRatio": info.get("pegRatio"),
            "evToEbitda": info.get("enterpriseToEbitda"),
            "priceToFreeCashFlow": (info.get("marketCap") / info.get("freeCashflow")) if info.get("marketCap") and info.get("freeCashflow") else None,
            "returnOnEquity": info.get("returnOnEquity"),
            "returnOnInvestedCapital": calculate_roic(),
            "operatingMargin": info.get("operatingMargins"),
            "netProfitMargin": info.get("profitMargins"),
            "debtToEquity": info.get("debtToEquity"),
            "netDebtToEbitda": ((info.get("totalDebt", 0) - info.get("totalCash", 0)) / info.get("ebitda")) if info.get("ebitda") else None,
            "currentRatio": info.get("currentRatio"),
            "quickRatio": info.get("quickRatio"),
            "revenueCAGR5Yr": calculate_revenue_cagr_5y(),
            "dividendYield": info.get("dividendYield"),
            "totalShareholderYield": calculate_shareholder_yield(),
            "payoutRatio": info.get("payoutRatio"),
        }

        return {
            "status": "success",
            "ticker": ticker_symbol,
            "fundamentals": metrics
        }
    
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

if __name__ == "__main__":
    # Start the server on port 8080
    uvicorn.run(app, host="0.0.0.0", port=8080)

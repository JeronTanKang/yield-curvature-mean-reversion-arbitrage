"""
1. CORPORATE - TREASURY SPREAD ARBITRAGE: using spread between corporate bond and treasury yield to determine signals
    - if corporate bond yield is significantly above treasury yield (exceeds threshold) this bond is underbalued => buy

    Issues with this strat:
    - each firm has unique credit risk situation. the rise in its yield might be justified
        - use CDS to validate the change in yield.
        - use NLP sentiment analysis on news to track updates on firm.

2. CREDIT SPREAD CURVE ABITRAGE
    - fix a firm/sector. If its 5-year bond has a 300 bp spread over treasury, while 10-year bond has 250bp spread => sell 5-year and buy 10-year anticipating spread to normalize.
    - improvement from strat 1 because it detects anomalies across a firm's yield curve rather than just comparing to a benchmark like treasuries

3. SECTOR SPREAD TRADING

4. PAIRS TRADING 
    - minimizes exposure to factors that affect the market such as interest rates, focusing on spread between the two bonds.

"""


# Install required packages
# pip install pandas numpy fredapi scipy matplotlib

import pandas as pd
import numpy as np
from fredapi import Fred  # FRED API
from scipy.optimize import minimize
import matplotlib.pyplot as plt

# FRED API key setup
fred = Fred(api_key='ec8283d904f5ccff891762f4ecdcac25') 

# Fetch multiple maturities from FRED
def fetch_yield_curve_data():
    maturities = {
        '2Y': 'DGS2',
        '5Y': 'DGS5',
        '10Y': 'DGS10',
        '30Y': 'DGS30'
    }
    yield_data = {}
    for key, fred_id in maturities.items():
        data = fred.get_series(fred_id, start='2022-01-01', end='2023-01-01')
        yield_data[key] = data
    yield_curve_data = pd.DataFrame(yield_data)
    yield_curve_data = yield_curve_data.ffill()  # Use forward fill for missing data
    yield_curve_data = yield_curve_data.reset_index()  # Reset index to make the 'date' column
    yield_curve_data.columns = ['date'] + list(maturities.keys())  # Rename the columns
    return yield_curve_data

# Function to calculate bond duration
def calculate_duration(coupon_rate, maturity, yield_to_maturity, face_value=1000):
    periods = int(maturity)
    coupon = coupon_rate * face_value
    present_value_of_cash_flows = sum([(coupon / (1 + yield_to_maturity) ** t) for t in range(1, periods + 1)])
    present_value_of_face_value = face_value / (1 + yield_to_maturity) ** maturity
    bond_price = present_value_of_cash_flows + present_value_of_face_value
    
    weighted_maturity = sum([t * (coupon / (1 + yield_to_maturity) ** t) for t in range(1, periods + 1)])
    weighted_maturity += maturity * (face_value / (1 + yield_to_maturity) ** maturity)
    
    duration = weighted_maturity / bond_price
    return duration

# Function to calculate bond convexity
def calculate_convexity(coupon_rate, maturity, yield_to_maturity, face_value=1000):
    periods = int(maturity)
    coupon = coupon_rate * face_value
    convexity = sum([t * (t + 1) * (coupon / (1 + yield_to_maturity) ** (t + 2)) for t in range(1, periods + 1)])
    convexity += maturity * (maturity + 1) * (face_value / (1 + yield_to_maturity) ** (maturity + 2))
    
    return convexity / face_value

# Function to construct replicating portfolio using optimization
def replicate_bond(target_bond, bond_pool):
    target_duration = target_bond['duration']
    target_convexity = target_bond['convexity']
    
    def objective_function(weights):
        portfolio_duration = sum([weights[i] * bond['duration'] for i, bond in enumerate(bond_pool)])
        portfolio_convexity = sum([weights[i] * bond['convexity'] for i, bond in enumerate(bond_pool)])
        
        return (portfolio_duration - target_duration) ** 2 + (portfolio_convexity - target_convexity) ** 2
    
    initial_weights = np.ones(len(bond_pool)) / len(bond_pool)
    constraints = [{'type': 'eq', 'fun': lambda w: np.sum(w) - 1}]
    bounds = [(0, 1)] * len(bond_pool)
    
    result = minimize(objective_function, initial_weights, bounds=bounds, constraints=constraints)
    
    if result.success:
        return result.x  # Optimized weights
    else:
        raise ValueError("Optimization failed")

# Function to calculate relative value deviation
def calculate_relative_value_deviation(target_bond, replicating_portfolio_yield):
    return target_bond['yield'] - replicating_portfolio_yield

# Function to generate trade signals
def screen_for_arbitrage_opportunities(bond_data, yield_curve, threshold=0.005):
    signals = []
    for index, bond in bond_data.iterrows():
        bond_maturity = bond['maturity']
        bond_yield = bond['yield']
        
        # Determine the appropriate yield from the U.S. Treasury curve based on maturity
        if bond_maturity <= 2:
            benchmark_yield = yield_curve['2Y'].iloc[index]
        elif bond_maturity <= 5:
            benchmark_yield = yield_curve['5Y'].iloc[index]
        elif bond_maturity <= 10:
            benchmark_yield = yield_curve['10Y'].iloc[index]
        else:
            benchmark_yield = yield_curve['30Y'].iloc[index]
        
        # Calculate the yield spread
        yield_spread = bond_yield - benchmark_yield
        
        # Generate signals if spread exceeds threshold
        if yield_spread > threshold:
            signals.append((bond['name'], "Sell Signal: Bond overpriced relative to benchmark"))
        elif yield_spread < -threshold:
            signals.append((bond['name'], "Buy Signal: Bond underpriced relative to benchmark"))
    
    return signals

# Visualization of yield curve and arbitrage signals
def visualize_yield_curve(yield_curve_data, signals):
    # Plot each maturity yield curve
    plt.plot(yield_curve_data['date'], yield_curve_data['2Y'], label="2Y Yield")
    plt.plot(yield_curve_data['date'], yield_curve_data['5Y'], label="5Y Yield")
    plt.plot(yield_curve_data['date'], yield_curve_data['10Y'], label="10Y Yield")
    plt.plot(yield_curve_data['date'], yield_curve_data['30Y'], label="30Y Yield")
    
    # Highlight signals using the dates of the arbitrage opportunities
    for signal in signals:
        signal_date = yield_curve_data['date'].iloc[0]  # Use the date of the signal if available
        plt.axvline(x=signal_date, color='red', linestyle='--', label=f"{signal[1]} on {signal_date}")
    
    plt.xlabel('Date')
    plt.ylabel('Yield (%)')
    plt.title('U.S. Treasury Yield Curve with Arbitrage Opportunities')
    plt.legend()
    plt.xticks(rotation=45)
    plt.show()

def main():
    # Fetch yield curve data from FRED
    yield_curve_data = fetch_yield_curve_data()  
    
    bond_pool = pd.DataFrame({
        'name': ['Corp Bond A', 'Corp Bond B', 'Corp Bond C'],
        'maturity': [5, 10, 30],  # Maturity in years
        'yield': [0.035, 0.04, 0.045]  # Corporate bond yields
    })
    
    # Generate trade signals based on yield curve spreads
    signals = screen_for_arbitrage_opportunities(bond_pool, yield_curve_data)
    
    # Visualize the yield curve and trade signals
    visualize_yield_curve(yield_curve_data, signals)

if __name__ == "__main__":
    main()


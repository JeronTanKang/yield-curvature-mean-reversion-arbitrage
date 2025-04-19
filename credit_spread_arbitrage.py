"""
to do:

1. target_spread_closure (and arbitrage_threshold): backtest to find optimal values 

Follow a heuristic like this:
If a target_spread_closure of 0.001 closes 80% of trades within 30 days and generates a moderate profit, 
but a 0.005 target achieves closure 90% of the time with slightly higher profits and shorter holding periods, 
the latter would likely be a better choice.

2. 


"""




import pandas as pd

pd.set_option('display.max_columns', None)

nrows = 20000000

# Load your bond data
df1 = pd.read_csv('/Users/jerontan/Desktop/y3s1/fixed income/BondDailyPublic.csv', nrows=nrows)
df2_raw = pd.read_csv('/Users/jerontan/Desktop/y3s1/fixed income/BondDailyDataPublic.csv', nrows=nrows)

# Ensure df2 has only one row per cusip_id by dropping duplicates (to prevent cartesian product when doing left join)
df2 = df2_raw.drop_duplicates(subset=['cusip_id'], keep='first')


# Add issuer_id as the first 6 characters of cusip_id
df1['issuer_id'] = df1['cusip_id'].str[:6]

# Merge the dataframes based on 'cusip_id'
df = pd.merge(df1, df2[['cusip_id', 'maturity']], on=['cusip_id'], how='left')

# Remove cs outliers (e.g., -1% to 10%)
df = df[(df['cs'] >= -0.01) & (df['cs'] <= 0.15)]

# Ensure 'cusip_id', 'cs', 'maturity', 'prclean', and 'trd_exctn_dt' are not missing
df = df.dropna(subset=['cusip_id', 'cs', 'maturity', 'prclean', 'trd_exctn_dt'])

# Convert 'maturity' and 'trd_exctn_dt' to datetime and normalize dates to remove time component
df['trd_exctn_dt'] = pd.to_datetime(df['trd_exctn_dt'], errors='coerce').dt.normalize()
df['maturity'] = pd.to_datetime(df['maturity'], errors='coerce').dt.normalize()

# Drop rows where 'maturity' could not be converted
df = df.dropna(subset=['maturity'])



# Calculate the count of each cusip_id
df['cusip_id_count'] = df.groupby('cusip_id')['cusip_id'].transform('count')
# Filter the dataframe to only keep rows where cusip_id count is greater than or equal to 15
df = df[df['cusip_id_count'] >= 15]
# Drop the helper column 'cusip_id_count' as it's no longer needed
df = df.drop(columns=['cusip_id_count'])
# Show the updated number of rows after filtering
rows_after_filtering = df.shape[0]
print(f"Number of rows after filtering cusip_id with count < 15: {rows_after_filtering}")



rows_before = df.shape[0]
print(f"Number of rows before dropping duplicates: {rows_before}")
# Keep only distinct rows
df = df.drop_duplicates()
# Show the number of rows after dropping duplicates
rows_after = df.shape[0]
print(f"Number of rows after dropping duplicates: {rows_after}")



# Function to calculate arbitrage threshold
def calculate_arbitrage_threshold(df, n_std=0.75):
    # Ensure necessary columns are not missing
    df = df.dropna(subset=['cusip_id', 'cs', 'maturity'])
    
    # Sort by issuer and maturity
    df = df.sort_values(by=['issuer_id', 'maturity'])

    # Create a shifted maturity column to compare with the previous maturity within each group
    df['maturity_shift'] = df.groupby('issuer_id')['maturity'].shift(1)

    # Apply the difference calculation within each group of 'issuer_id'
    df['cs_diff'] = df.groupby('issuer_id', group_keys=False).apply(
        lambda group: group['cs'].diff().where(group['maturity'] != group['maturity_shift'])
    )

    # Drop NaN values resulting from the diff operation
    df = df.dropna(subset=['cs_diff'])

    # Calculate the overall mean and standard deviation for all issuers combined
    mean_diff = df['cs_diff'].mean()
    std_diff = df['cs_diff'].std()

    # Calculate a global arbitrage threshold
    arbitrage_threshold = mean_diff - (n_std * std_diff)

    return arbitrage_threshold, mean_diff, std_diff




# Set an arbitrage threshold for mispricing
arbitrage_threshold = calculate_arbitrage_threshold(df, n_std=2)[0]
print('arbitrage_threshold:', arbitrage_threshold)
# Updated logic to capture both cusip_id for short and long bonds
# Arbitrage Opportunities List
arbitrage_opportunities = []

# Group bonds by issuer (issuer_id) and compare credit spreads
print("Grouping by issuer_id and checking for arbitrage opportunities...")

grouped = df.groupby('issuer_id')
min_rows = 64

def is_in_last_20_rows(df, cusip_id, open_date):
    # Get the last 20 trade execution dates for the given cusip_id
    last_20_dates = df[df['cusip_id'] == cusip_id]['trd_exctn_dt'].nlargest(20)
    # Check if the open_date is in the last 20 rows
    return open_date in last_20_dates.values


from pandas.tseries.offsets import Day
for name, group in grouped:
    if len(group) < min_rows:
        continue

    group = group.sort_values(['maturity', 'trd_exctn_dt'])  # Sort by both maturity and execution date

    # Logic to find arbitrage based on Credit Spread (cs) differences
    for i in range(1, len(group)):
        # Ensure maturities are different before checking for arbitrage
        if group['maturity'].iloc[i] != group['maturity'].iloc[i - 1]:
            # Check if both bonds were traded within a 2-day window
            date_diff = abs(group['trd_exctn_dt'].iloc[i] - group['trd_exctn_dt'].iloc[i - 1])
            if date_diff <= Day(15):  # Allow up to 2-day difference in trade execution dates
                # Check if the short bond's open date is not in the last 20 rows for that cusip_id
                if not is_in_last_20_rows(df, group['cusip_id'].iloc[i - 1], group['trd_exctn_dt'].iloc[i - 1]):
                    spread_diff = group['cs'].iloc[i] - group['cs'].iloc[i - 1]

                    if spread_diff < arbitrage_threshold:
                        print(f"Potential Arbitrage: Shorter-maturity bond has higher CS than longer-maturity bond for issuer {name}")
                        print(f"Bond with maturity {group['maturity'].iloc[i-1]} CS: {group['cs'].iloc[i-1]}")
                        print(f"Bond with maturity {group['maturity'].iloc[i]} CS: {group['cs'].iloc[i]}")

                        # Capture the opportunity details, now including both cusip_id
                        arbitrage_opportunities.append({
                            'issuer_id': name,  # issuer identifier (first 6 chars of cusip_id)
                            'cusip_id_short': group['cusip_id'].iloc[i - 1],  # cusip_id for the shorter maturity bond
                            'cusip_id_long': group['cusip_id'].iloc[i],  # cusip_id for the longer maturity bond
                            'shorter_maturity_bond': group['maturity'].iloc[i - 1],
                            'longer_maturity_bond': group['maturity'].iloc[i],
                            'open_date_short': group['trd_exctn_dt'].iloc[i - 1],
                            'open_date_long': group['trd_exctn_dt'].iloc[i]
                        })

                        # Limit to first 5 opportunities
                        if len(arbitrage_opportunities) == 5:
                            break
    if len(arbitrage_opportunities) == 5:
        break



print(f"Identified {len(arbitrage_opportunities)} arbitrage opportunities.")



# Standardize date handling for the arbitrage trades
def execute_arbitrage_trades(df, arbitrage_opportunities, target_spread_closure=0.001, max_hold_period=30):
    trades_log = []

    for opportunity in arbitrage_opportunities:
        cusip_id_short = opportunity['cusip_id_short']  # cusip_id for the shorter maturity bond
        cusip_id_long = opportunity['cusip_id_long']  # cusip_id for the longer maturity bond
        shorter_maturity_bond = pd.Timestamp(opportunity['shorter_maturity_bond']).normalize()
        longer_maturity_bond = pd.Timestamp(opportunity['longer_maturity_bond']).normalize()
        open_date_short = pd.Timestamp(opportunity['open_date_short']).normalize()
        open_date_long = pd.Timestamp(opportunity['open_date_long']).normalize()

        # Attempt to fetch short bond's price data on the open date
        short_price_open = df.loc[
            (df['cusip_id'] == cusip_id_short) &
            (df['maturity'] == shorter_maturity_bond) &
            (df['trd_exctn_dt'] == open_date_short), 'prclean'
        ]
        short_price_open = short_price_open.iloc[0]
        print('======> short_price_open:', short_price_open)

        # Use a similar approach for the long bond's price data
        long_price_open = df.loc[
            (df['cusip_id'] == cusip_id_long) &
            (df['maturity'] == longer_maturity_bond) &
            (df['trd_exctn_dt'] == open_date_long), 'prclean'
        ]
        long_price_open = long_price_open.iloc[0]
        
        # Initial spread calculation
        initial_spread = short_price_open - long_price_open
        print('initial_spread:',initial_spread)
        
        for day in range(1, max_hold_period + 1):
            trade_date = (open_date_short + pd.Timedelta(days=day)).normalize()

            # Fetch closing prices for both the short and long bonds
            short_price_data_close = df.loc[
                (df['cusip_id'] == cusip_id_short) & 
                (df['maturity'] == shorter_maturity_bond) & 
                (df['trd_exctn_dt'] == trade_date), 'prclean'
            ]


            if short_price_data_close.empty:
                print(f"INFO: No closing data for shorter maturity bond: {cusip_id_short} on {trade_date}")
                continue

            short_price_close = short_price_data_close.values[0]

            long_price_data_close = df.loc[
                (df['cusip_id'] == cusip_id_long) & 
                (df['maturity'] == longer_maturity_bond) & 
                (df['trd_exctn_dt'] == trade_date), 'prclean'
            ]


            if long_price_data_close.empty:
                print(f"INFO: No closing data for longer maturity bond: {cusip_id_long} on {trade_date}")
                continue

            long_price_close = long_price_data_close.values[0]
            
            # Spread closure calculation
            current_spread = short_price_close - long_price_close
            spread_closure = initial_spread - current_spread

            # Check if arbitrage spread closure condition is met
            print('spread_closure:',spread_closure)
            if spread_closure >= target_spread_closure:
                profit = (short_price_close - short_price_open) + (long_price_open - long_price_close)
                trades_log.append({
                    'cusip_id_short': cusip_id_short,
                    'cusip_id_long': cusip_id_long,
                    'open_date': open_date_short,
                    'close_date': trade_date,
                    'short_price_open': short_price_open,
                    'long_price_open': long_price_open,
                    'short_price_close': short_price_close,
                    'long_price_close': long_price_close,
                    'profit': profit,
                    'holding_period': day
                })
                break
            else:
                # If no arbitrage opportunity is closed within the max holding period
                profit = (short_price_close - short_price_open) + (long_price_open - long_price_close)
                trades_log.append({
                    'cusip_id_short': cusip_id_short,
                    'cusip_id_long': cusip_id_long,
                    'open_date': open_date_short,
                    'close_date': trade_date,
                    'short_price_open': short_price_open,
                    'long_price_open': long_price_open,
                    'short_price_close': short_price_close,
                    'long_price_close': long_price_close,
                    'profit': profit,
                    'holding_period': max_hold_period
                })

    trades_log_df = pd.DataFrame(trades_log)
    return trades_log_df



# Execute the trades
trades_log_df = execute_arbitrage_trades(df, arbitrage_opportunities)

# View the trades log
print(trades_log_df)

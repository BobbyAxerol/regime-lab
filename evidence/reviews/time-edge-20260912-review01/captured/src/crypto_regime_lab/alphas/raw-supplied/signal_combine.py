import pandas as pd
import numpy as np
from ta.volatility import AverageTrueRange
from ta.trend import SMAIndicator
from ta.volume import MFIIndicator
from ta.momentum import RSIIndicator

params = {
    'coeff' : 4,
    'AP' : 11,
    'novolumedata': False, 
    'src_col': 'close',
    'regime_threshold': 65
}

def cal_TA(data, params):
    
    #lay params và khoi tạo =============================================================================================//
    data = data.copy()
    coeff = int(params['coeff'])
    AP = int(params['AP'])
    novolumedata = params['novolumedata']
    src_col = params['src_col']
    regime_threshold = params['regime_threshold']
    
    data['trend'] = 0.0
    data['buy_signal'] = False
    data['sell_signal'] = False
    data['long_signal'] = False
    data['short_signal'] = False
    data['buy_signal_approved'] = False
    data['sell_signal_approved'] = False
    data['upT'] = np.nan
    data['downT'] = np.nan
    
    # TA calculations ============================================================================================================//
    atr_indicator = AverageTrueRange(high=data['high'], low=data['low'], close=data['close'], window=AP, fillna=False)

    if novolumedata or 'volume' not in data.columns:
        condition_indicator = RSIIndicator(close=data[src_col], window=AP, fillna=False)
    else:   #mot la dung RSI hay MFI
        condition_indicator = MFIIndicator(
            high=data['high'], low=data['low'], close=data['close'], volume=data['volume'], window=AP, fillna=False
        )
    
    for i in range(1, len(data)):
        atr = atr_indicator.average_true_range().iloc[:i+1].iloc[-1]
        condition = condition_indicator.rsi().iloc[:i+1].iloc[-1] >= regime_threshold if novolumedata else condition_indicator.money_flow_index().iloc[:i+1].iloc[-1] >= regime_threshold
        
        data.loc[data.index[i], 'upT'] = data['low'].iloc[i] - atr * coeff
        data.loc[data.index[i], 'downT'] = data['high'].iloc[i] + atr * coeff
        
        prev_alpha = data['trend'].iloc[i-1]
        if condition:
            data.loc[data.index[i], 'trend'] = data['upT'].iloc[i] if data['upT'].iloc[i] > prev_alpha else prev_alpha
        else:
            data.loc[data.index[i], 'trend'] = data['downT'].iloc[i] if data['downT'].iloc[i] < prev_alpha else prev_alpha
        #(nếu thị trường tăng với điều kiện MFI/RSI > 50, trend tăng dầu, ngược lại trend giảm dần)
    
    return data

def generate_signals(data):
    data = data.copy()

    alpha_trend = data['trend']
    alpha_trend_2 = data['trend'].shift(2)
    data['buy_signal'] = (alpha_trend > alpha_trend_2) & (alpha_trend.shift(1) <= alpha_trend_2) 
    #(so sánh tại (i và i -2) và (i - 1 và i - 2)
    data['sell_signal'] = (alpha_trend < alpha_trend_2) & (alpha_trend.shift(1) >= alpha_trend_2)
    #(tạo tín hiệu cơ bản dựa trên trend hiện tại và trước đó làm cơ sở tính toán đếm số nến k1, k2, o1, o2)

    
    # Calculate bars since signals (K1, K2, O1, O2)
    data['K1'] = np.nan
    data['K2'] = np.nan
    data['O1'] = np.nan
    data['O2'] = np.nan
    
    for i in range(1, len(data)):
        # K1: Bars since last buy_signal
        if data['buy_signal'].iloc[i]:
            data.loc[data.index[i], 'K1'] = 0
        elif i > 0 and pd.notna(data['K1'].iloc[i-1]):
            data.loc[data.index[i], 'K1'] = data['K1'].iloc[i-1] + 1
        
        # K2: Bars since last sell_signal
        if data['sell_signal'].iloc[i]:
            data.loc[data.index[i], 'K2'] = 0 
        elif i > 0 and pd.notna(data['K2'].iloc[i-1]):
            data.loc[data.index[i], 'K2'] = data['K2'].iloc[i-1] + 1
        
        # O1: Bars since previous buy_signal
        if data['buy_signal'].iloc[i-1] if i > 0 else False:
            data.loc[data.index[i], 'O1'] = 0
        elif i > 1 and pd.notna(data['O1'].iloc[i-1]):
            data.loc[data.index[i], 'O1'] = data['O1'].iloc[i-1] + 1
        
        # O2: Bars since previous sell_signal
        if data['sell_signal'].iloc[i-1] if i > 0 else False:
            data.loc[data.index[i], 'O2'] = 0
        elif i > 1 and pd.notna(data['O2'].iloc[i-1]):
            data.loc[data.index[i], 'O2'] = data['O2'].iloc[i-1] + 1
    
    # Generate long/short signals
    data['long_signal'] = data['buy_signal'] & (data['O1'] > data['K2'])
    data['short_signal'] = data['sell_signal'] & (data['O2'] > data['K1'])
    
    # dùng shift để giảm nhiễu
    data['buy_signal_approved'] = (data['buy_signal'].shift(1) & (data['O1'].shift(1) > data['K2'].shift(1)))
    data['sell_signal_approved'] = (data['sell_signal'].shift(1) & (data['O2'].shift(1) > data['K1'].shift(1)))
    
    return data

def main(data, params):
    data = cal_TA(data, params)
    data = generate_signals(data)
    return data

def apply_SigCombine_strategy(data, params):
    data = main(data, params)
    data['Position'] = 0
    pos = 0
    
    for i in range(1, len(data)):
        if pos >= 1 and data['short_signal'].iloc[i]:
            pos = 0
            data.loc[data.index[i], 'Position'] = pos

        elif pos <= -1 and data['long_signal'].iloc[i]:
            pos = 0
            data.loc[data.index[i], 'Position'] = pos

        if pos == 0:
            if data['long_signal'].iloc[i]:
                pos = 2
                data.loc[data.index[i], 'Position'] = pos

            elif data['short_signal'].iloc[i]:
                pos = 0
                data.loc[data.index[i], 'Position'] = pos

        else:
            data.loc[data.index[i], 'Position'] = pos
    
    return data
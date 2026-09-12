import numpy as np
import pandas as pd
from numba import njit

# --- 1. HÀM HỖ TRỢ CHUẨN PINESCRIPT (TỐI ƯU HÓA O(N)) ---

@njit
def n_sma(src, length):
    out = np.zeros_like(src)
    asum = 0.0
    for i in range(length):
        asum += src[i]
    out[length-1] = asum / length
    for i in range(length, len(src)):
        asum += src[i] - src[i-length]
        out[i] = asum / length
    return out

@njit
def n_stdev(src, length):
    out = np.zeros_like(src)
    n = len(src)
    if n < length:
        return out
    asum = 0.0
    asum_sq = 0.0
    for i in range(length):
        val = src[i]
        asum += val
        asum_sq += val * val
    var = (asum_sq - (asum * asum) / length) / (length - 1)
    out[length - 1] = np.sqrt(max(0.0, var))
    for i in range(length, n):
        old_val = src[i - length]
        new_val = src[i]
        asum += new_val - old_val
        asum_sq += new_val * new_val - old_val * old_val
        var = (asum_sq - (asum * asum) / length) / (length - 1)
        out[i] = np.sqrt(max(0.0, var))
    return out

@njit
def n_rsi(close, length):
    n = len(close)
    rsi = np.zeros(n)
    gains = np.zeros(n)
    losses = np.zeros(n)
    for i in range(1, n):
        diff = close[i] - close[i-1]
        gains[i] = max(diff, 0)
        losses[i] = max(-diff, 0)
    avg_gain = np.mean(gains[1:length+1])
    avg_loss = np.mean(losses[1:length+1])
    if avg_loss == 0:
        rsi[length] = 100
    else:
        rsi[length] = 100 - (100 / (1 + (avg_gain / avg_loss)))
    for i in range(length + 1, n):
        avg_gain = (avg_gain * (length - 1) + gains[i]) / length
        avg_loss = (avg_loss * (length - 1) + losses[i]) / length
        if avg_loss == 0:
            rsi[i] = 100
        else:
            rsi[i] = 100 - (100 / (1 + (avg_gain / avg_loss)))
    return rsi

@njit
def n_atr(high, low, close, length):
    n = len(close)
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
    atr = np.zeros(n)
    atr[length] = np.mean(tr[1:length+1])
    for i in range(length + 1, n):
        atr[i] = (atr[i-1] * (length - 1) + tr[i]) / length
    return atr

@njit
def n_vwap_daily(high, low, close, volume, new_day):
    n = len(close)
    vwap = np.zeros(n)
    cum_pv = 0.0
    cum_vol = 0.0
    for i in range(n):
        if new_day[i]:
            cum_pv = 0.0
            cum_vol = 0.0
        hlc3 = (high[i] + low[i] + close[i]) / 3.0
        cum_pv += hlc3 * volume[i]
        cum_vol += volume[i]
        vwap[i] = cum_pv / cum_vol if cum_vol != 0 else hlc3
    return vwap

# --- 2. CORE SIGNAL ENGINE (CHỈ TÍNH TOÁN VỊ THẾ TRẠNG THÁI) ---

@njit
def core_vwap_mean_reversion_logic(
    open_p, high_p, low_p, close_p, vwap_p,
    rsi_p, atr_p, htf_ema_p,
    rsi_os, rsi_ob, dev_mult, stop_atr, target_r,
    exit_at_vwap, time_stop_on, time_stop_bars
):
    n = len(close_p)
    pos = np.zeros(n)
    
    curr_pos = 0  # 1: Long, -1: Short
    entry_price = 0.0
    entry_bar = 0
    stop_loss = 0.0
    fixed_tp = 0.0
    
    dev_len = 50
    dist = close_p - vwap_p
    dist_sma = n_sma(dist, dev_len)
    dist_std = n_stdev(dist, dev_len)
    
    for t in range(max(dev_len, 200), n):
        z = (dist[t] - dist_sma[t]) / dist_std[t] if dist_std[t] != 0 else 0.0
        exited_this_bar = False
        
        # --- 2.1 LOGIC THOÁT LỆNH ---
        if curr_pos != 0:
            # a. Time Stop
            if time_stop_on and (t - entry_bar) >= time_stop_bars:
                curr_pos = 0
                exited_this_bar = True
            
            # b. Thoát vị thế Long
            elif curr_pos == 1:
                if low_p[t] <= stop_loss:          # Hit SL
                    curr_pos = 0
                    exited_this_bar = True
                elif exit_at_vwap and high_p[t] >= vwap_p[t]: # Hit Dynamic VWAP
                    curr_pos = 0
                    exited_this_bar = True
                elif high_p[t] >= fixed_tp:        # Hit Fixed TP
                    curr_pos = 0
                    exited_this_bar = True
            
            # c. Thoát vị thế Short
            elif curr_pos == -1:
                if high_p[t] >= stop_loss:          # Hit SL
                    curr_pos = 0
                    exited_this_bar = True
                elif exit_at_vwap and low_p[t] <= vwap_p[t]:  # Hit Dynamic VWAP
                    curr_pos = 0
                    exited_this_bar = True
                elif low_p[t] <= fixed_tp:         # Hit Fixed TP
                    curr_pos = 0
                    exited_this_bar = True

        # --- 2.2 LOGIC VÀO LỆNH ---
        elif curr_pos == 0 and not exited_this_bar:
            trend_long_ok = close_p[t] >= htf_ema_p[t]
            trend_short_ok = close_p[t] <= htf_ema_p[t]
            
            # Long Entry
            if trend_long_ok and z <= -dev_mult and rsi_p[t] <= rsi_os:
                curr_pos = 1
                entry_price = close_p[t]
                entry_bar = t
                risk_dist = atr_p[t] * stop_atr
                stop_loss = entry_price - risk_dist
                fixed_tp = entry_price + risk_dist * target_r
            
            # Short Entry
            elif trend_short_ok and z >= dev_mult and rsi_p[t] >= rsi_ob:
                curr_pos = -1
                entry_price = close_p[t]
                entry_bar = t
                risk_dist = atr_p[t] * stop_atr
                stop_loss = entry_price + risk_dist
                fixed_tp = entry_price - risk_dist * target_r
        
        pos[t] = curr_pos
        
    return pos

# --- 3. WRAPPER GENERATOR (CHỈ TRẢ VỀ CỘT TÍN HIỆU) ---

def generate_vwap_signals(df, p):
    df = df.sort_index()
    
    c = df['close'].values
    h = df['high'].values
    l = df['low'].values
    v = df['volume'].values
    
    # Phát hiện ngày mới để tính toán VWAP
    dates = df.index.date
    new_day = np.zeros(len(df), dtype=np.bool_)
    new_day[0] = True
    new_day[1:] = dates[1:] != dates[:-1]
    
    vwap = n_vwap_daily(h, l, c, v, new_day)
    rsi = n_rsi(c, p['rsi_len'])
    atr = n_atr(h, l, c, p['atr_len'])
    
    # Đồng bộ đa khung thời gian HTF (Chống Look-Ahead Bias)
    df_htf = df.resample(p['htf_tf']).agg({'close': 'last'})
    df_htf['ema'] = df_htf['close'].ewm(span=p['htf_ema_len'], adjust=False).mean()
    df_htf['ema_shifted'] = df_htf['ema'].shift(1)
    df_htf = df_htf.dropna(subset=['ema_shifted'])
    
    df_main_tmp = df.copy()
    df_main_tmp['_match_time'] = df_main_tmp.index
    df_htf_tmp = df_htf[['ema_shifted']].copy()
    df_htf_tmp['_match_time'] = df_htf_tmp.index
    
    merged = pd.merge_asof(
        df_main_tmp,
        df_htf_tmp,
        on='_match_time',
        direction='backward'
    )
    htf_ema = merged['ema_shifted'].ffill().values
    
    # Tính toán mảng vị thế
    pos_weight = core_vwap_mean_reversion_logic(
        df['open'].values, h, l, c, vwap,
        rsi, atr, htf_ema,
        p['rsi_os'], p['rsi_ob'], p['dev_mult'], p['stop_atr'], p['target_r'],
        p['exit_at_vwap'], p['time_stop_on'], p['time_stop_bars']
    )
    
    df['pos_weight'] = pos_weight
    return df


baba = {'rsi_len': 59, 'rsi_os': 47, 'rsi_ob': 77, 'dev_mult': 3.5, 'atr_len': 57, 'stop_atr': 7.300000000000001, 'target_r': 4.2, 'htf_ema_len': 450, 'exit_at_vwap': False, 'time_stop_on': False, 'time_stop_bars': 105} # 5m/eth, đường k oke.
bubu = {'rsi_len': 21, 'rsi_os': 45, 'rsi_ob': 76, 'dev_mult': 1.5, 'atr_len': 14, 'stop_atr': 6.300000000000001, 'target_r': 8.700000000000001, 'htf_ema_len': 570, 'exit_at_vwap': False, 'time_stop_on': False, 'time_stop_bars': 105}  #15m eth, đường pnl oke, nhưng đánh hơi ít nhen
byby = {'rsi_len': 68, 'rsi_os': 21, 'rsi_ob': 77, 'dev_mult': 1.3, 'atr_len': 45, 'stop_atr': 2.7, 'target_r': 1.2000000000000002, 'htf_ema_len': 350, 'exit_at_vwap': False, 'time_stop_on': True, 'time_stop_bars': 5} #1m eth
tete = {'rsi_len': 16, 'rsi_os': 18, 'rsi_ob': 63, 'dev_mult': 4.1, 'atr_len': 77, 'stop_atr': 8.9, 'target_r': 3.4000000000000004, 'htf_ema_len': 130, 'exit_at_vwap': False, 'time_stop_on': False, 'time_stop_bars': 15} #5m vn30f1m
keke = {'capital_risk_pct': 7.8, 'max_pos_size': 663.0, 'sl_pct': 0.07050000000000001, 'tp_pct': 0.196} # # 5/30 sol
btbt = {'cetp_window': 7, 'cetp_bins': 4, 'decay_factor': 0.55, 'body_weight': 8.5, 'upper_weight': 2.1, 'lower_weight': 5.9, 'long_threshold_base': 2.91, 'short_threshold_base': -1.25, 'cetp_k': 1.5000000000000002, 'mom_scale': 10.0, 'min_score_strength': 0.6900000000000001, 'min_price_move_mult': 3.75, 'min_vol_mult': 8.2, 'vol_threshold_limit': 3.0, 'stop_loss_pct': 1.1, 'stop_loss_pct_short': 5.8, 'atr_mult': 3.0, 'trail_mult': 13.5, 'trail_offset_pct': 1.6, 'max_hold_bars': 77} # 15m btc, đường oke, nhưng đánh quá ít.
bebe = {'cetp_window': 37, 'cetp_bins': 8, 'decay_factor': 1.55, 'body_weight': 2.0, 'upper_weight': 4.4, 'lower_weight': 1.7000000000000002, 'long_threshold_base': 1.76, 'short_threshold_base': -0.75, 'cetp_k': 3.9000000000000004, 'mom_scale': 2.0, 'min_score_strength': 0.99, 'min_price_move_mult': 4.25, 'min_vol_mult': 8.0, 'vol_threshold_limit': 15.0, 'stop_loss_pct': 6.6, 'stop_loss_pct_short': 1.5000000000000002, 'atr_mult': 5.800000000000001, 'trail_mult': 4.5, 'trail_offset_pct': 5.7, 'max_hold_bars': 53} # 1h btc, không được, đánh quá ít
bibi = {'cetp_window': 9, 'cetp_bins': 2, 'decay_factor': 0.6, 'body_weight': 9.5, 'upper_weight': 2.1, 'lower_weight': 1.7000000000000002, 'long_threshold_base': 3.61, 'short_threshold_base': -1.0, 'cetp_k': 1.9000000000000001, 'mom_scale': 4.0, 'min_score_strength': 2.2, 'min_price_move_mult': 3.25, 'min_vol_mult': 1.6, 'vol_threshold_limit': 32.0, 'stop_loss_pct': 4.6, 'stop_loss_pct_short': 1.9000000000000001, 'atr_mult': 9.4, 'trail_mult': 16.5, 'trail_offset_pct': 5.2, 'max_hold_bars': 77} #4h btc, không được, bỏ luôn, 1d cũng k có hy vọng gì.
brbr = {'cetp_window': 38, 'cetp_bins': 19, 'decay_factor': 1.2000000000000002, 'body_weight': 2.0, 'upper_weight': 0.1, 'lower_weight': 2.1, 'long_threshold_base': 1.36, 'short_threshold_base': -0.19999999999999973, 'cetp_k': 3.0000000000000004, 'mom_scale': 1.0, 'min_score_strength': 0.39, 'min_price_move_mult': 8.5, 'min_vol_mult': 7.4, 'vol_threshold_limit': 38.0, 'stop_loss_pct': 6.5, 'stop_loss_pct_short': 4.7, 'atr_mult': 6.800000000000001, 'trail_mult': 6.0, 'trail_offset_pct': 6.4, 'max_hold_bars': 77} # 15m bnb
bfbf = {'cetp_window': 6, 'cetp_bins': 5, 'decay_factor': 2.35, 'body_weight': 1.5, 'upper_weight': 2.6, 'lower_weight': 4.2, 'long_threshold_base': 0.16000000000000003, 'short_threshold_base': -2.5, 'cetp_k': 2.6, 'mom_scale': 29.0, 'min_score_strength': 0.97, 'min_price_move_mult': 1.75, 'min_vol_mult': 3.8000000000000003, 'vol_threshold_limit': 32.0, 'stop_loss_pct': 1.0, 'stop_loss_pct_short': 4.5, 'atr_mult': 6.0, 'trail_mult': 5.0, 'trail_offset_pct': 2.8000000000000003, 'max_hold_bars': 43} #1h bnb, số được, nhưng pnl tàm tạm thôi.
bqbq = {'cetp_window': 23, 'cetp_bins': 18, 'decay_factor': 0.6, 'body_weight': 7.5, 'upper_weight': 0.7000000000000001, 'lower_weight': 3.3000000000000003, 'long_threshold_base': 0.6100000000000001, 'short_threshold_base': -3.35, 'cetp_k': 8.6, 'mom_scale': 20.0, 'min_score_strength': 1.31, 'min_price_move_mult': 2.25, 'min_vol_mult': 1.6, 'vol_threshold_limit': 40.0, 'stop_loss_pct': 1.4000000000000001, 'stop_loss_pct_short': 2.0, 'atr_mult': 9.200000000000001, 'trail_mult': 3.5, 'trail_offset_pct': 1.8, 'max_hold_bars': 41} # 4h bnb số đẹp, nhưng đường pnl hơi chán
bcbc = {'cetp_window': 28, 'cetp_bins': 15, 'decay_factor': 1.55, 'body_weight': 9.5, 'upper_weight': 2.3000000000000003, 'lower_weight': 1.8, 'long_threshold_base': 0.51, 'short_threshold_base': -0.7999999999999998, 'cetp_k': 3.0000000000000004, 'mom_scale': 16.0, 'min_score_strength': 0.13, 'min_price_move_mult': 1.75, 'min_vol_mult': 1.4, 'vol_threshold_limit': 40.0, 'stop_loss_pct': 3.5000000000000004, 'stop_loss_pct_short': 4.0, 'atr_mult': 5.6000000000000005, 'trail_mult': 6.5, 'trail_offset_pct': 5.5, 'max_hold_bars': 9} # 1d bnb, chans số thì đẹp nhưng pnl chán lắm
bnbn = {'cetp_window': 36, 'cetp_bins': 14, 'decay_factor': 3.2, 'body_weight': 1.0, 'upper_weight': 1.1, 'lower_weight': 5.2, 'long_threshold_base': 0.9600000000000001, 'short_threshold_base': -0.19999999999999973, 'cetp_k': 0.8, 'mom_scale': 20.0, 'min_score_strength': 0.33, 'min_price_move_mult': 1.5, 'min_vol_mult': 5.6000000000000005, 'vol_threshold_limit': 30.0, 'stop_loss_pct': 1.5000000000000002, 'stop_loss_pct_short': 4.6, 'atr_mult': 2.4000000000000004, 'trail_mult': 13.0, 'trail_offset_pct': 9.5, 'max_hold_bars': 45} #1h sol
bvbv = {'cetp_window': 33, 'cetp_bins': 17, 'decay_factor': 3.1, 'body_weight': 2.5, 'upper_weight': 2.8000000000000003, 'lower_weight': 2.7, 'long_threshold_base': 0.91, 'short_threshold_base': -2.5, 'cetp_k': 9.2, 'mom_scale': 15.0, 'min_score_strength': 2.22, 'min_price_move_mult': 3.25, 'min_vol_mult': 3.2, 'vol_threshold_limit': 3.0, 'stop_loss_pct': 0.5, 'stop_loss_pct_short': 3.9000000000000004, 'atr_mult': 9.200000000000001, 'trail_mult': 20.5, 'trail_offset_pct': 2.2, 'max_hold_bars': 39} # 4h sol
base = {
    'htf_tf': '1h',
}

params = {**tete, **base}
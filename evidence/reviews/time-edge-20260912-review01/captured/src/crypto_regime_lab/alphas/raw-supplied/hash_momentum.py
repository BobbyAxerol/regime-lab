from numba import njit

# --- PHẦN 1: TÍNH TOÁN CHỈ BÁO ---
@njit
def calculate_indicators(close, mom_len, ema_len):
    n = len(close)
    # 1. Momentum
    mom0 = np.zeros(n)
    for i in range(mom_len, n):
        mom0[i] = close[i] - close[i - mom_len]
    
    # 2. Normalized Momentum (Z-score style)
    mom_std = np.zeros(n)
    mom_norm = np.zeros(n)
    for i in range(mom_len * 3, n):
        mom_std[i] = np.std(mom0[i - (mom_len*3) + 1 : i + 1])
        if mom_std[i] > 0:
            mom_norm[i] = mom0[i] / mom_std[i]
            
    # 3. ATR (Mô phỏng ta.atr)
    atr = np.zeros(n)
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(close[i]-close[i-1], abs(close[i]-close[i-1])) 
    
    alpha = 1.0 / 14
    atr[14] = np.mean(tr[1:15])
    for i in range(15, n):
        atr[i] = alpha * tr[i] + (1 - alpha) * atr[i-1]
        
    # 4. EMA
    alpha_ema = 2.0 / (ema_len + 1)
    ema = np.zeros(n)
    ema[0] = close[0]
    for i in range(1, n):
        ema[i] = alpha_ema * close[i] + (1 - alpha_ema) * ema[i-1]
        
    return mom0, mom_norm, atr, ema


@njit
def execute_hash_momentum_backtest(close, high, low, mom0, mom_norm, atr, ema, 
                                  initial_capital, trading_fee, cooldown_bars,
                                  stop_loss_perc, rr_ratio, tp1_ratio, 
                                  tp1_qty_perc, tp2_ratio, tp2_qty_perc, 
                                  mom_threshold_mult, usd_per_trade): # Thêm tham số mới
    n = len(close)
    equity = np.zeros(n)
    equity[:] = initial_capital
    pos_size = np.zeros(n) 
    
    curr_units = 0.0
    entry_p = 0.0
    stop_p = 0.0
    tp_final_p = 0.0
    tp1_p = 0.0
    tp2_p = 0.0
    
    tp1_done = False
    tp2_done = False
    last_trade_bar = -cooldown_bars
    fee = trading_fee / 100.0

    for i in range(1, n):
        equity[i] = equity[i-1]
        
        if curr_units != 0:
            side = 1 if curr_units > 0 else -1
            is_hit_sl = (side == 1 and low[i] <= stop_p) or (side == -1 and high[i] >= stop_p)
            is_hit_tp_final = (side == 1 and high[i] >= tp_final_p) or (side == -1 and low[i] <= tp_final_p)
            
            if is_hit_sl:
                equity[i] += curr_units * (stop_p - entry_p) - (abs(curr_units) * stop_p * fee)
                curr_units = 0.0; last_trade_bar = i
            
            elif not tp1_done:
                hit_tp1 = (side == 1 and high[i] >= tp1_p) or (side == -1 and low[i] <= tp1_p)
                if hit_tp1:
                    close_qty = curr_units * (tp1_qty_perc / 100.0)
                    equity[i] += close_qty * (tp1_p - entry_p) - (abs(close_qty) * tp1_p * fee)
                    curr_units -= close_qty
                    tp1_done = True
            
            elif not tp2_done:
                hit_tp2 = (side == 1 and high[i] >= tp2_p) or (side == -1 and low[i] <= tp2_p)
                if hit_tp2:
                    close_qty = curr_units * (tp2_qty_perc / 100.0)
                    equity[i] += close_qty * (tp2_p - entry_p) - (abs(close_qty) * tp2_p * fee)
                    curr_units -= close_qty
                    tp2_done = True
            
            elif is_hit_tp_final:
                equity[i] += curr_units * (tp_final_p - entry_p) - (abs(curr_units) * tp_final_p * fee)
                curr_units = 0.0; last_trade_bar = i

        # --- LOGIC VÀO LỆNH VỚI USD_PER_TRADE ---
        if curr_units == 0 and (i - last_trade_bar >= cooldown_bars):
            dyn_threshold = atr[i] * mom_threshold_mult
            mom1 = mom0[i] - mom0[i-1]
            
            # Kiểm tra xem vốn còn đủ usd_per_trade không
            if equity[i] >= usd_per_trade:
                if mom0[i] > dyn_threshold and mom1 > 0 and mom_norm[i] > 0.5 and close[i] > close[i-1] and close[i] > ema[i]:
                    entry_p = close[i]
                    stop_p = entry_p * (1 - stop_loss_perc / 100.0)
                    risk = entry_p - stop_p
                    tp1_p = entry_p + (risk * tp1_ratio)
                    tp2_p = entry_p + (risk * tp2_ratio)
                    tp_final_p = entry_p + (risk * rr_ratio)
                    
                    curr_units = usd_per_trade / entry_p # Khối lượng tính theo số tiền cố định
                    equity[i] -= (usd_per_trade * fee)
                    tp1_done = tp2_done = False
                    
                elif mom0[i] < -dyn_threshold and mom1 < 0 and mom_norm[i] < -0.5 and close[i] < close[i-1] and close[i] < ema[i]:
                    entry_p = close[i]
                    stop_p = entry_p * (1 + stop_loss_perc / 100.0)
                    risk = stop_p - entry_p
                    tp1_p = entry_p - (risk * tp1_ratio)
                    tp2_p = entry_p - (risk * tp2_ratio)
                    tp_final_p = entry_p - (risk * rr_ratio)
                    
                    curr_units = -usd_per_trade / entry_p
                    equity[i] -= (usd_per_trade * fee)
                    tp1_done = tp2_done = False

        pos_size[i] = curr_units
    return pos_size, equity

def run_hash_strategy(df, params):
    c = df['close'].values.astype(np.float64)
    h = df['high'].values.astype(np.float64)
    l = df['low'].values.astype(np.float64)
    
    mom0, mom_norm, atr, ema = calculate_indicators(c, params['mom_len'], params['ema_len'])
    
    pos, eq = execute_hash_momentum_backtest(
        c, h, l, mom0, mom_norm, atr, ema,
        initial_capital    = float(params['initial_capital']),
        trading_fee        = float(params['trading_fee']),
        cooldown_bars      = int(params['cooldown_bars']),
        stop_loss_perc     = float(params['stop_loss_perc']),
        rr_ratio           = float(params['rr_ratio']),
        tp1_ratio          = float(params['tp1_ratio']),
        tp1_qty_perc       = float(params['tp1_qty_perc']),
        tp2_ratio          = float(params['tp2_ratio']),
        tp2_qty_perc       = float(params['tp2_qty_perc']),
        mom_threshold_mult = float(params['mom_threshold_mult']),
        usd_per_trade      = float(params['usd_per_trade']),
    )
    
    df['Position_Units'] = pos
    df['Equity'] = eq
    df['Position'] = np.where(pos > 0, 1, np.where(pos < 0, -1, 0))
    return df

huhu = {'mom_len': 20, 'mom_threshold_mult': 3.75, 'ema_len': 30, 'stop_loss_perc': 5.5, 'rr_ratio': 3.2, 'tp1_ratio': 2.4000000000000004, 'tp1_qty_perc': 55, 'tp2_ratio': 2.1, 'tp2_qty_perc': 65, 'cooldown_bars': 10}
hihi = {'mom_len': 11, 'mom_threshold_mult': 1.0, 'ema_len': 38, 'stop_loss_perc': 6.0, 'rr_ratio': 3.6, 'tp1_ratio': 2.7, 'tp1_qty_perc': 50, 'tp2_ratio': 2.9000000000000004, 'tp2_qty_perc': 60, 'cooldown_bars': 4}
bubu = {'mom_len': 18, 'mom_threshold_mult': 5.0, 'ema_len': 36, 'stop_loss_perc': 5.5, 'rr_ratio': 1.1, 'tp1_ratio': 2.9000000000000004, 'tp1_qty_perc': 50, 'tp2_ratio': 3.8, 'tp2_qty_perc': 30, 'cooldown_bars': 5}
haft = {'mom_len': 10, 'mom_threshold_mult': 5.25, 'ema_len': 44, 'stop_loss_perc': 2.2, 'rr_ratio': 3.1, 'tp1_ratio': 2.1, 'tp1_qty_perc': 30, 'tp2_ratio': 1.4, 'tp2_qty_perc': 45, 'cooldown_bars': 8} # 4h eth
kaka = {'mom_len': 27, 'mom_threshold_mult': 2.5, 'ema_len': 24, 'stop_loss_perc': 5.0, 'rr_ratio': 2.8, 'tp1_ratio': 1.3, 'tp1_qty_perc': 60, 'tp2_ratio': 1.7, 'tp2_qty_perc': 55, 'cooldown_bars': 25} #5m eth
kuku = {'mom_len': 54, 'mom_threshold_mult': 5.75, 'ema_len': 44, 'stop_loss_perc': 6.5, 'rr_ratio': 2.7, 'tp1_ratio': 1.3, 'tp1_qty_perc': 60, 'tp2_ratio': 3.7, 'tp2_qty_perc': 30, 'cooldown_bars': 29} #5m eth signal notional

"""
Loại bỏ những logic và tham số về account config, chỉ để lại logic chính và tham số chính để dùng quantbt
"""
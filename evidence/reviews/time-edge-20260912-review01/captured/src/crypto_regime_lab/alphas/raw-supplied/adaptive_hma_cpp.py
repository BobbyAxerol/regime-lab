import numpy as np
import pandas as pd
from numba import njit

# ─── SECTION 1: CÁC HÀM CHỈ BÁO KỸ THUẬT VÀ HELPER ĐỘNG CHO NUMBA ───

@njit(fastmath=True)
def n_ema(src, length):
    alpha = 2.0 / (length + 1)
    out = np.zeros_like(src)
    out[0] = src[0]
    for i in range(1, len(src)):
        out[i] = alpha * src[i] + (1.0 - alpha) * out[i-1]
    return out

@njit(fastmath=True)
def n_atr(h, l, c, length):
    tr = np.zeros_like(c)
    tr[0] = h[0] - l[0]
    for i in range(1, len(c)):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1]))
    return n_ema(tr, length)

@njit(fastmath=True)
def n_rsi(src, length):
    n = len(src)
    out = np.zeros_like(src)
    if n <= length:
        return out
    gains = np.zeros_like(src)
    losses = np.zeros_like(src)
    for i in range(1, n):
        diff = src[i] - src[i-1]
        gains[i] = max(diff, 0.0)
        losses[i] = max(-diff, 0.0)
    
    sum_gain = 0.0
    sum_loss = 0.0
    for i in range(1, length + 1):
        sum_gain += gains[i]
        sum_loss += losses[i]
    avg_gain = sum_gain / length
    avg_loss = sum_loss / length
    
    if avg_loss == 0.0:
        out[length] = 100.0 if avg_gain > 0.0 else 50.0
    else:
        out[length] = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
        
    alpha = 1.0 / length 
    for i in range(length + 1, n):
        avg_gain = alpha * gains[i] + (1.0 - alpha) * avg_gain
        avg_loss = alpha * losses[i] + (1.0 - alpha) * avg_loss
        if avg_loss == 0.0:
            out[i] = 100.0
        else:
            out[i] = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    return out

@njit(fastmath=True)
def _xhma_at_t(src, t, length):
    """Tính toán Hull Moving Average động tại điểm t với chu kỳ length thay đổi liên tục"""
    if length <= 1:
        return src[t]
    half_len = int(length // 2)
    sqrt_len = int(np.floor(np.sqrt(length)))
    
    # Tính toán tổ hợp WMAs cho dải lùi phục vụ nến ngoài HMA
    outer_sum = 0.0
    outer_w_sum = 0.0
    for i in range(sqrt_len):
        curr_t = t - i
        if curr_t < 0: curr_t = 0
        
        # WMA (length / 2)
        s_half = 0.0
        w_half_sum = 0.0
        for j in range(half_len):
            idx = curr_t - j
            if idx < 0: idx = 0
            w = half_len - j
            s_half += src[idx] * w
            w_half_sum += w
        wma_half = s_half / w_half_sum if w_half_sum > 0 else src[curr_t]
        
        # WMA (length)
        s_full = 0.0
        w_full_sum = 0.0
        for j in range(length):
            idx = curr_t - j
            if idx < 0: idx = 0
            w = length - j
            s_full += src[idx] * w
            w_full_sum += w
        wma_full = s_full / w_full_sum if w_full_sum > 0 else src[curr_t]
        
        combined_val = 2.0 * wma_half - wma_full
        w_outer = sqrt_len - i
        outer_sum += combined_val * w_outer
        outer_w_sum += w_outer
        
    return outer_sum / outer_w_sum if outer_w_sum > 0 else src[t]

@njit(fastmath=True)
def _calcslope_at_t(ma_arr, t, high_arr, low_arr, close_arr):
    """Tính độ dốc chuẩn hóa góc hình học (Góc từ -180 đến 180 thực tế)"""
    # Tìm highest(34) và lowest(34)
    hh = high_arr[t]
    ll = low_arr[t]
    for i in range(1, 34):
        idx = t - i
        if idx < 0: idx = 0
        if high_arr[idx] > hh: hh = high_arr[idx]
        if low_arr[idx] < ll: ll = low_arr[idx]
        
    diff = hh - ll
    if diff == 0.0: diff = 1e-9
    slope_range = 25.0 / diff * ll
    
    t_prev2 = t - 2
    if t_prev2 < 0: t_prev2 = 0
    
    dt = (ma_arr[t_prev2] - ma_arr[t]) / (close_arr[t] + 1e-9) * slope_range
    c = np.sqrt(1.0 + dt * dt)
    
    acos_val = np.arccos(1.0 / c)
    xAngle = np.round(180.0 * acos_val / np.pi)
    
    return -xAngle if dt > 0.0 else xAngle


# ─── SECTION 2: LÕI MÁY TRẠNG THÁI KIỂM ĐỊNH ADAPTIVE HMA+ (THE STRATEGY BRAIN) ───

@njit(fastmath=True)
def core_adaptive_hma_signals(
    time_ms, close, high, low, volume,
    minLength, maxLength, minorMin, minorMax,
    flat, atrFast, atrSlow, mult, maxSL, takeProfit, minProfit,
    sl_input_mode, double_up
):
    n = len(close)
    
    # Bộ ba mảng đầu ra đồng bộ để triệt tiêu hoàn toàn Look-Ahead và Execution Bias
    pos_weight = np.zeros(n)
    exit_type = np.zeros(n)   # 0: Không thoát, 1: Dính SL, 2: Dính TP, 3: Thoát bằng Chỉ báo (RSI/HMA)
    exit_price = np.zeros(n)  # Giá chốt thoát thực tế phục vụ backtest ma trận
    
    # 2.1 Cấu trúc mảng chỉ báo cơ sở tĩnh bên ngoài
    atrBase = n_atr(high, low, close, 21)
    atr40 = n_atr(high, low, close, 40)
    atr_fast_arr = n_atr(high, low, close, atrFast)
    atr_slow_arr = n_atr(high, low, close, atrSlow)
    rsi_arr = n_rsi(close, 14)
    
    # Khởi tạo mảng động lưu HMA và Slope
    dynamicHMA = np.zeros(n)
    minorHMA = np.zeros(n)
    slope_arr = np.zeros(n)
    
    # Thiết lập độ lệch pip hệ thống tối ưu theo bước giá
    mintick = 0.0001 
    pip_size = mintick * 10.0 

    # Biến tích lũy chu kỳ thích ứng liên tục qua từng bar
    dynamicLength = (minLength + maxLength) / 2.0
    minorLength = (minorMin + minorMax) / 2.0
    adaptPct = 0.03141

    # Khởi tạo các biến quản lý trạng thái lệnh độc lập qua vòng lặp
    target_w = 0.0
    entry_price = 0.0
    buySL, buyTP = 0.0, 0.0
    sellSL, sellTP = 0.0, 0.0
    
    start_idx = max(maxLength, max(minorMax, max(atrSlow, 48))) + 10

    for t in range(2, n):
        # 2.2 Đồng bộ chu kỳ HMA Thích ứng theo độ biến động
        charged = atr_fast_arr[t] > atr_slow_arr[t]
        if charged:
            dynamicLength = max(minLength, dynamicLength * (1.0 - adaptPct))
            minorLength = max(minorMin, minorLength * (1.0 - adaptPct))
        else:
            dynamicLength = min(maxLength, dynamicLength * (1.0 + adaptPct))
            minorLength = min(minorMax, minorLength * (1.0 + adaptPct))
            
        dynamicHMA[t] = _xhma_at_t(close, t, int(dynamicLength))
        minorHMA[t] = _xhma_at_t(close, t, int(minorLength))
        slope_arr[t] = _calcslope_at_t(dynamicHMA, t, high, low, close)
        
        # Tính toán hệ thống dải băng khoảng cách (Distance Zone Envelope)
        upperTL = dynamicHMA[t] + mult * atr40[t]
        lowerTL = dynamicHMA[t] - mult * atr40[t]
        topTL = dynamicHMA[t] + (mult * 2.0) * atr40[t]
        botTL = dynamicHMA[t] - (mult * 2.0) * atr40[t]

        # Logic kiểm tra tín hiệu gốc của xu hướng tại nến t
        upSig = slope_arr[t] >= flat and charged
        dnSig = slope_arr[t] <= -flat and charged
        upSig_prev = slope_arr[t-1] >= flat and (atr_fast_arr[t-1] > atr_slow_arr[t-1])
        dnSig_prev = slope_arr[t-1] <= -flat and (atr_fast_arr[t-1] > atr_slow_arr[t-1])

        # ─── NGUYÊN TẮC KHÔNG BIAS: GÁN VỊ THẾ BƯỚC VÀO NẾN T TỪ TRẠNG THÁI CUỐI NẾN T-1 ───
        pos_weight[t] = target_w

        # --- LOGIC QUẢN LÝ VÀ THOÁT VỊ THẾ ĐANG CHẠY NỘI BAR (TÍNH TOÁN CHO NẾN T) ---
        exited_this_bar = False
        
        if target_w == 1.0: # ĐANG GIỮ LỆNH LONG MANG TỪ QUÁ KHỨ VÀO NẾN T
            minBuyProfit = entry_price + (minProfit * atrBase[t])
            RSIexitBuy = (rsi_arr[t] < 50.0) or (rsi_arr[t-1] >= 70.0 and rsi_arr[t] < 70.0)
            crossunder_HMA = (close[t-1] >= dynamicHMA[t-1]) and (close[t] < dynamicHMA[t])
            
            if low[t] <= buySL:  # 1. Dính Stop Loss nội bar (Ưu tiên bảo thủ trước)
                exit_type[t] = 1.0
                exit_price[t] = buySL
                target_w = 0.0
                exited_this_bar = True
            elif high[t] >= buyTP: # 2. Chạm Take Profit nội bar
                exit_type[t] = 2.0
                exit_price[t] = buyTP
                target_w = 0.0
                exited_this_bar = True
            elif close[t] >= minBuyProfit and (RSIexitBuy or crossunder_HMA): # 3. Thoát theo chỉ báo khi đóng nến t
                exit_type[t] = 3.0
                exit_price[t] = close[t]
                target_w = 0.0
                exited_this_bar = True
                
        elif target_w == -1.0: # ĐANG GIỮ LỆNH SHORT MANG TỪ QUÁ KHỨ VÀO NẾN T
            minSellProfit = entry_price - (minProfit * atrBase[t])
            RSIexitSell = (rsi_arr[t] > 50.0) or (rsi_arr[t-1] <= 30.0 and rsi_arr[t] > 30.0)
            crossover_HMA = (close[t-1] <= dynamicHMA[t-1]) and (close[t] > dynamicHMA[t])
            
            if high[t] >= sellSL:  # 1. Dính Stop Loss nội bar
                exit_type[t] = 1.0
                exit_price[t] = sellSL
                target_w = 0.0
                exited_this_bar = True
            elif low[t] <= sellTP: # 2. Chạm Take Profit nội bar
                exit_type[t] = 2.0
                exit_price[t] = sellTP
                target_w = 0.0
                exited_this_bar = True
            elif close[t] <= minSellProfit and (RSIexitSell or crossover_HMA): # 3. Thoát theo chỉ báo khi đóng nến t
                exit_type[t] = 3.0
                exit_price[t] = close[t]
                target_w = 0.0
                exited_this_bar = True

        # --- LOGIC ĐÁNH GIÁ VÀO VỊ THẾ MỚI (CHỐT ĐIỀU KIỆN TẠI GIÁ CLOSE NẾN T - VÀO LỆNH Ở NẾN T+1) ---
        if target_w == 0.0 and not exited_this_bar and t >= start_idx:
            SLLowMax = low[t] - (maxSL * atrBase[t])
            SLHighMax = high[t] + (maxSL * atrBase[t])
            
            hh_48 = high[t]
            ll_48 = low[t]
            for i in range(1, 48):
                idx = t - i
                if idx < 0: idx = 0
                if high[idx] > hh_48: hh_48 = high[idx]
                if low[idx] < ll_48: ll_48 = low[idx]
            lastHigh = hh_48 + (5.0 * pip_size)
            lastLow = ll_48 - (5.0 * pip_size)

            if sl_input_mode == 0:
                sl_buy_raw, sl_sell_raw = botTL, topTL
            elif sl_input_mode == 1:
                sl_buy_raw, sl_sell_raw = lowerTL, upperTL
            elif sl_input_mode == 2:
                sl_buy_raw, sl_sell_raw = lastLow, lastHigh
            else:
                sl_buy_raw, sl_sell_raw = SLLowMax, SLHighMax

            buy = upSig and not upSig_prev and close[t] > dynamicHMA[t] and low[t] <= upperTL and (51.0 < rsi_arr[t] <= 70.0)
            sell = dnSig and not dnSig_prev and close[t] < dynamicHMA[t] and high[t] >= lowerTL and (30.0 <= rsi_arr[t] < 49.0)
            
            overBuy = upSig and not upSig_prev and rsi_arr[t] > 70.0 and close[t] > dynamicHMA[t] and ((high[t] + low[t]) / 2.0) > upperTL and minorHMA[t] > dynamicHMA[t]
            overSell = dnSig and not dnSig_prev and rsi_arr[t] < 30.0 and close[t] < dynamicHMA[t] and ((high[t] + low[t]) / 2.0) < lowerTL and minorHMA[t] < dynamicHMA[t]

            if buy or overBuy:
                target_w = 1.0
                entry_price = close[t] # Điểm kích hoạt thực tế khớp tại giá Open nến t+1 (bằng Close nến t)
                buySL = sl_buy_raw if SLLowMax < sl_buy_raw else SLLowMax
                buyTP = high[t] + (takeProfit * atrBase[t])
                
            elif sell or overSell:
                target_w = -1.0
                entry_price = close[t]
                sellSL = sl_sell_raw if SLHighMax > sl_sell_raw else SLHighMax
                sellTP = low[t] - (takeProfit * atrBase[t])

    return pos_weight, exit_type, exit_price


# ─── SECTION 3: WRAPPER PYTHON ĐỒNG BỘ DATAFRAME PANDAS ───

def generate_adaptive_hma_signals(df, p):
    """
    df: DataFrame OHLCV chứa các cột dữ liệu ['high', 'low', 'close', 'volume']
    p: dictionary chứa các tham số tối ưu hóa của hệ thống
    """
    df = df.copy()
    time_ms = df.index.values.astype(np.int64) // 10**6
    c = df['close'].values.astype(np.float64)
    h = df['high'].values.astype(np.float64)
    l = df['low'].values.astype(np.float64)
    v = df['volume'].values.astype(np.float64)
    
    # 0: One Distance Zone, 1: Half Distance Zone, 2: Last High/Low, 3: ATR Only
    sl_mode_map = {"One Distance Zone": 0, "Half Distance Zone": 1, "Last High/Low": 2, "ATR Only": 3}
    sl_input_mode = sl_mode_map.get(p.get('sl_input', 'Half Distance Zone'), 1)

    # Nhận cấu trúc 3 mảng an toàn từ lỗi xử lý phi nhân quả
    pos, e_type, e_price = core_adaptive_hma_signals(
        time_ms, c, h, l, v,
        int(p['min_length']), int(p['max_length']), int(p['minor_min']), int(p['minor_max']),
        float(p['flat']), int(p['atr_fast']), int(p['atr_slow']), float(p['mult']),
        float(p['max_sl']), float(p['take_profit']), float(p['min_profit']),
        sl_input_mode, bool(p.get('double_up', False))
    )
    
    # Đồng bộ hóa dữ liệu vào DataFrame
    df['pos_weight'] = pos
    df['exit_type'] = e_type
    df['exit_price'] = e_price
    
    return df



ghgh = {'min_length': 184, 'max_length': 344, 'minor_min': 68, 'minor_max': 134, 'flat': 34.0, 'atr_fast': 9, 'atr_slow': 38, 'mult': 1.4, 'min_profit': 2.3, 'take_profit': 6.300000000000001, 'max_sl': 6.7, 'sl_mult': 1.4} #15m eth, đường đẹp lẫn số đẹp nốt
hyhy = {'min_length': 172, 'max_length': 384, 'minor_min': 36, 'minor_max': 124, 'flat': 31.5, 'atr_fast': 14, 'atr_slow': 52, 'mult': 3.6, 'min_profit': 0.5, 'take_profit': 5.9, 'max_sl': 6.1000000000000005, 'sl_mult': 1.1} #1h eth, đường siêu đẹp, số cũng đẹp nốt.
hfhf = {'min_length': 292, 'max_length': 232, 'minor_min': 42, 'minor_max': 160, 'flat': 24.5, 'atr_fast': 41, 'atr_slow': 106, 'mult': 5.0, 'min_profit': 0.8, 'take_profit': 5.5, 'max_sl': 6.4, 'sl_mult': 2.1} #4h eth, nói chung cũng được á, chỉ là không bằng 1h
htht = {'min_length': 120, 'max_length': 244, 'minor_min': 92, 'minor_max': 184, 'flat': 30.0, 'atr_fast': 17, 'atr_slow': 30, 'mult': 5.0, 'min_profit': 2.3, 'take_profit': 4.2, 'max_sl': 6.7, 'sl_mult': 1.4}  # 1d eth

gege = {'min_length': 276, 'max_length': 308, 'minor_min': 56, 'minor_max': 108, 'flat': 41.5, 'atr_fast': 38, 'atr_slow': 46, 'mult': 4.7, 'min_profit': 2.4, 'take_profit': 3.6, 'max_sl': 5.6, 'sl_mult': 1.7000000000000002}  #1h btc, cũng được, những phải wf
hjhj = {'min_length': 320, 'max_length': 204, 'minor_min': 78, 'minor_max': 166, 'flat': 24.5, 'atr_fast': 8, 'atr_slow': 64, 'mult': 3.0, 'min_profit': 3.2, 'take_profit': 4.7, 'max_sl': 7.0, 'sl_mult': 2.4000000000000004} #1d btc, không được đánh ít quá.

bvbv = {'min_length': 124, 'max_length': 348, 'minor_min': 74, 'minor_max': 172, 'flat': 23.0, 'atr_fast': 44, 'atr_slow': 76, 'mult': 1.3, 'min_profit': 3.2, 'take_profit': 5.1, 'max_sl': 3.9000000000000004, 'sl_mult': 2.3} #1h sol, Oke nhé
bcbc = {'min_length': 212, 'max_length': 360, 'minor_min': 98, 'minor_max': 104, 'flat': 19.0, 'atr_fast': 33, 'atr_slow': 120, 'mult': 4.5, 'min_profit': 3.3, 'take_profit': 4.4, 'max_sl': 7.4, 'sl_mult': 2.4000000000000004}  #1d sol, đánh ít quá.

bgbg = {'min_length': 288, 'max_length': 348, 'minor_min': 54, 'minor_max': 180, 'flat': 9.0, 'atr_fast': 7, 'atr_slow': 52, 'mult': 1.4, 'min_profit': 1.5000000000000002, 'take_profit': 2.3, 'max_sl': 7.0, 'sl_mult': 2.3} #1h bnb, oke quá
bjbj = {'min_length': 212, 'max_length': 324, 'minor_min': 62, 'minor_max': 132, 'flat': 16.5, 'atr_fast': 24, 'atr_slow': 50, 'mult': 3.7, 'min_profit': 0.4, 'take_profit': 6.0, 'max_sl': 6.5, 'sl_mult': 1.5} #1d bnb

bobo = {'min_length': 124, 'max_length': 356, 'minor_min': 38, 'minor_max': 118, 'flat': 24.0, 'atr_fast': 36, 'atr_slow': 80, 'mult': 2.0, 'min_profit': 1.8, 'take_profit': 5.300000000000001, 'max_sl': 4.5, 'sl_mult': 1.5} #1h doge, đẹp chiến

hoho = {'min_length': 248, 'max_length': 200, 'minor_min': 62, 'minor_max': 184, 'flat': 23.5, 'atr_fast': 25, 'atr_slow': 120, 'mult': 2.9000000000000004, 'min_profit': 3.0, 'take_profit': 6.0, 'max_sl': 3.9000000000000004, 'sl_mult': 1.7000000000000002} #5m vn30f1m, cũng oke
hbhb = {'min_length': 308, 'max_length': 280, 'minor_min': 32, 'minor_max': 154, 'flat': 11.5, 'atr_fast': 18, 'atr_slow': 70, 'mult': 4.1, 'min_profit': 0.8, 'take_profit': 2.1, 'max_sl': 3.3, 'sl_mult': 0.5} #1h vn30f1m, số thì đẹp nhưng đánh ít quá.

import numpy as np
from scipy.ndimage import median_filter

def median_filter_1d(data, window_size=3):
    """
    一维中值滤波
    window_size: 窗口大小，建议1-3个点（对于2Hz采样率）
    """
    if window_size % 2 == 0:
        window_size += 1  # 确保是奇数
    return median_filter(data, size=window_size, mode='nearest')

def hampel_filter(data, window_size=3, n_sigma=3):
    """
    Hampel滤波（基于中位绝对偏差的异常值检测）
    
    参数:
    - data: 输入数据
    - window_size: 窗口大小，建议1-3个点
    - n_sigma: 阈值倍数，默认3
    """
    if window_size % 2 == 0:
        window_size += 1  # 确保是奇数
    
    half_window = window_size // 2
    filtered_data = data.copy()
    
    for i in range(len(data)):
        # 确定窗口范围
        start = max(0, i - half_window)
        end = min(len(data), i + half_window + 1)
        window_data = data[start:end]
        
        # 计算中位数
        median = np.median(window_data)
        
        # 计算中位绝对偏差 (MAD)
        mad = np.median(np.abs(window_data - median))
        
        # 估计标准差: sigma ≈ 1.4826 * MAD
        sigma = 1.4826 * mad if mad > 0 else 0
        
        # 判断是否为异常值
        if np.abs(data[i] - median) > n_sigma * sigma:
            # 用中位数替换异常值
            filtered_data[i] = median
        else:
            # 保留原值
            filtered_data[i] = data[i]
    
    return filtered_data
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np

def main():
    file_path = 'execution_log_linux.csv'
    print(f"Reading log file: {file_path}")
    
    try:
        # Load the data
        df = pd.read_csv(file_path)
        
        # Clean data: drop rows where Latency_us is 'TIMEOUT'
        df['Latency_us'] = df['Latency_us'].astype(str)
        df_valid = df[df['Latency_us'] != 'TIMEOUT'].copy()
        df_valid['Latency_us'] = pd.to_numeric(df_valid['Latency_us'])
        
        # Convert Timestamp_us to relative time in seconds for plotting
        df_valid['Timestamp_us'] = pd.to_numeric(df_valid['Timestamp_us'])
        start_time = df_valid['Timestamp_us'].min()
        df_valid['Time_s'] = (df_valid['Timestamp_us'] - start_time) / 1_000_000.0

        print("Data loading and cleaning successful.")
        print(f"Total valid packets: {len(df_valid)}")
        print(f"Total TIMEOUTs: {len(df) - len(df_valid)}")
        
        if len(df_valid) == 0:
            print("No valid data to plot.")
            return

        # --- Statistical Analysis ---
        mean_lat = df_valid['Latency_us'].mean()
        median_lat = df_valid['Latency_us'].median()
        min_lat = df_valid['Latency_us'].min()
        max_lat = df_valid['Latency_us'].max()
        p95_lat = np.percentile(df_valid['Latency_us'], 95)
        p99_lat = np.percentile(df_valid['Latency_us'], 99)

        print("\n=== Linux HFT Latency Statistics ===")
        print(f"Mean:   {mean_lat:.2f} us")
        print(f"Median: {median_lat:.2f} us")
        print(f"Min:    {min_lat:.2f} us")
        print(f"Max:    {max_lat:.2f} us")
        print(f"95th %: {p95_lat:.2f} us")
        print(f"99th %: {p99_lat:.2f} us")
        print("====================================\n")

        # --- Plotting ---
        sns.set_theme(style="whitegrid")
        
        # Create a figure with subplots
        fig = plt.figure(figsize=(15, 10))
        
        # 1. Line plot over time (Scatter is better for dense data)
        ax1 = fig.add_subplot(2, 2, 1)
        sns.scatterplot(data=df_valid, x='Time_s', y='Latency_us', alpha=0.3, s=5, ax=ax1, color='blue', edgecolor=None)
        ax1.set_title('Latency Over Time (Scatter)')
        ax1.set_xlabel('Time (seconds)')
        ax1.set_ylabel('Latency (us)')
        
        # 2. Histogram
        ax2 = fig.add_subplot(2, 2, 2)
        sns.histplot(data=df_valid, x='Latency_us', bins=50, kde=True, ax=ax2, color='green')
        ax2.set_title('Latency Distribution')
        ax2.set_xlabel('Latency (us)')
        ax2.set_ylabel('Count')
        
        # 3. Boxplot
        ax3 = fig.add_subplot(2, 2, 3)
        sns.boxplot(data=df_valid, y='Latency_us', ax=ax3, color='orange', showfliers=True)
        ax3.set_title('Latency Boxplot (Showing Outliers)')
        ax3.set_ylabel('Latency (us)')
        
        # 4. Results Bar Chart
        ax4 = fig.add_subplot(2, 2, 4)
        sns.countplot(data=df_valid, x='Result', ax=ax4, order=['SELL', 'HOLD', 'BUY'], palette='Set2')
        ax4.set_title('Prediction Results Distribution')
        ax4.set_xlabel('Prediction')
        ax4.set_ylabel('Count')

        plt.suptitle('FPGA HFT System Performance Analysis (Linux)', fontsize=16)
        plt.tight_layout()
        
        out_file = 'linux_performance_analysis.png'
        plt.savefig(out_file, dpi=300)
        print(f"Saved plots to '{out_file}'")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == '__main__':
    main()

import React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from "recharts";


export type DataPoint = { time: string; value: number, type: string };

export const allFrequencies: Record<string, string> = {
    '5T': "Day",
    '30T': "Week",
    '1H': "Month",
    '6H': "Bi-Month",
    '12H': "Quarter",
    '1D': "Year",
    '2D': "Bi-Year",
    '5D': "All"
}

const StockGraph: React.FC<{ data: DataPoint[] }> = React.memo(({ data }) => {
  console.log("update")
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data}>
        <CartesianGrid stroke="#eee" strokeDasharray="5 5" />
          <XAxis
            dataKey="time"
            tickFormatter={(timeStr: string) => {
              const date = new Date(timeStr);
              const year = date.getFullYear();
              const month = (date.getMonth() + 1).toString().padStart(2, '0');
              const day = date.getDate().toString().padStart(2, '0');
              const hours = date.getHours().toString().padStart(2, '0');
              const minutes = date.getMinutes().toString().padStart(2, '0');
              return `${year}/${month}/${day} ${hours}:${minutes}`;
            }}
            interval={Math.floor(data.length / 15)}
            angle={-90}
            textAnchor="end"
            height={200}
          />
        <YAxis domain={[
          (dataMin: number) => dataMin - (Math.max(...data.map(d => d.value)) - Math.min(...data.map(d => d.value))) / 25,
          'auto'
        ]}/>
        <Tooltip
          formatter={(value: number, _: string, props: any) => {
            const timeStr = props?.payload?.time; // get from your data object
            const date = new Date(timeStr);
            const formattedTime = date.toLocaleString();
            const formattedValue = Number(value).toFixed(2).toString() + "€";

            return [
              <div key="tooltip-content">
                <div>Date: {formattedTime}</div>
                <div>Value: {formattedValue}</div>
              </div>
            ];
          }}
        />
        <Line
          type="monotone"
          dataKey="value"
          stroke="red"
          strokeWidth={3}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
});

export default StockGraph;
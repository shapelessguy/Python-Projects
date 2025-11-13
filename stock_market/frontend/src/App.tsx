import { useEffect, useState, useRef } from "react";
import "./App.css"
import StockGraph, { allFrequencies, type DataPoint } from "./Graph"


function App() {
  const [_, setStatus] = useState(null);
  const [data, setData] = useState<Record<string, any>>({});
  const selectedTicker = useRef<string>("");
  const selectedFreq = useRef<string>("1D");
  const [graphData, setGraphData] = useState<DataPoint[]>([]);
  const [updates, setUpdates] = useState({});
  const [loading, setLoading] = useState(true);

  const API_BASE = "http://localhost:8000";

  async function fetchStatus() {
    const res = await fetch(`${API_BASE}/status`);
    const json = await res.json();
    setStatus(json);
  }

  async function fetchAll() {
    const res = await fetch(`${API_BASE}/get_all`);
    const json = await res.json();
    const data: DataPoint[] = json.data;
    setData(data || {});
  }

  async function updateGraph() {
    try {
      const res = await fetch(`${API_BASE}/get_stock?stock=${selectedTicker.current}&freq=${selectedFreq.current}`);
      const json = await res.json();
      const data: DataPoint[] = json.data;
      if (selectedTicker.current && data) {
        setGraphData(data);
      }
      else {
        setGraphData([]);
      }
    } catch (err) {
      setGraphData([]);
      console.error("Failed to fetch data", err);
    }
  }

  async function fetchUpdates() {
    const res = await fetch(`${API_BASE}/get_updates`);
    const json = await res.json();
    setUpdates(json.data || {});
  }

  useEffect(() => {
    async function load() {
      // await fetchStatus();
      // await fetchAll();
      setLoading(false);
    }
    load();

    const interval = setInterval(() => {
      fetchUpdates();
    }, 500);

    return () => clearInterval(interval);
  }, []);

  if (loading) return <p>Loading...</p>;

  return (
    <div style={{ display: "block", padding: "20px", fontFamily: "sans-serif", height: "100vh", boxSizing: "border-box", margin: 0 }}>
      <h1>Stock Monitoring</h1>

      <div style={{display: "flex", flex: 1, flexDirection: "row", marginBottom: "30px", maxHeight: "calc(100% - 120px)" }}>
        <div style={{display: "flex", flexDirection: "column", flex: 1, padding: "10px", minWidth: "300px", maxWidth: "300px"}}>
          <section style={{display: "flex", flexDirection: "column", overflowY: "auto" }}>
            <h2>Real time</h2>
            {Object.keys(updates).length === 0 ? (
              <p>No updates yet</p>
            ) : (
              Object.entries(updates).map(([key, value]: any) => (
                <div key={key} style={{display: "flex", flexDirection: "column", maxHeight: "100%"}}>
                  <button className="ticker" onClick={() => { selectedTicker.current = key; updateGraph(); }}>
                    <b>{key}</b>: {value.value}
                  </button>
                </div>
              ))
            )}
          </section>
        </div>

        <div style={{padding: "10px", minWidth: "1000px", maxWidth: "1000px", marginRight: "50px", minHeight: "500px", maxHeight: "500px"}}>
          <StockGraph data={graphData}/>
        </div>
        <div style={{display: "flex", flexDirection: "column"}}>
          {Object.entries(allFrequencies).map(([k, v]) => {
            return (
              <button key={k} className="ticker" onClick={() => { selectedFreq.current = k; updateGraph(); }}>
                <b>{v}</b>
              </button>
            )
          })}
        </div>

      </div>


    </div>
  );
}

export default App;

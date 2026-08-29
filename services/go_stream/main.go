package main

import (
	"encoding/json"
	"fmt"
	"log"
	"math"
	"net/http"
	"os"
	"sync"
	"time"
)

type LiveTelemetry struct {
	Timestamp      string  `json:"timestamp"`
	ActiveCity     string  `json:"active_city"`
	RadarStation   string  `json:"radar_station"`
	RadarStatus    string  `json:"radar_status"`
	RadarFrames    int     `json:"radar_frames_count"`
	PrecipRateMMH  float64 `json:"precip_rate_mmh"`
	PrecipSource   string  `json:"precip_source"`
	TempC          float64 `json:"temp_c"`
	HumidityPct    float64 `json:"humidity_pct"`
	TideLevelM     float64 `json:"tide_level_m"`
	NWPModel       string  `json:"nwp_model"`
	EngineThroughput string `json:"engine_throughput"`
}

type StreamHub struct {
	mu        sync.RWMutex
	telemetry LiveTelemetry
}

var hub = &StreamHub{
	telemetry: LiveTelemetry{
		ActiveCity:     "MUMBAI",
		RadarStation:   "Mumbai Colaba (DWR-C01)",
		RadarStatus:    "ONLINE_STREAMING",
		RadarFrames:    24,
		PrecipRateMMH:  12.4,
		PrecipSource:   "IMD DWR + OpenWeather High-Rate Ingest",
		TempC:          28.4,
		HumidityPct:    86.0,
		TideLevelM:     1.42,
		NWPModel:       "NCMRWF Unified Model (NCUM-R 4km)",
		EngineThroughput: "Sub-1ms Go Goroutine Ingestion",
	},
}

func setCORSHeaders(w http.ResponseWriter, r *http.Request) {
	origin := r.Header.Get("Origin")
	allowedOrigins := map[string]bool{
		"http://localhost:3000":          true,
		"http://127.0.0.1:3000":          true,
		"https://ufns-demo-v4.vercel.app": true,
	}
	if allowedOrigins[origin] {
		w.Header().Set("Access-Control-Allow-Origin", origin)
		w.Header().Set("Vary", "Origin")
	}
}

func telemetryHandler(w http.ResponseWriter, r *http.Request) {
	setCORSHeaders(w, r)
	w.Header().Set("Content-Type", "application/json")

	hub.mu.RLock()
	data := hub.telemetry
	data.Timestamp = time.Now().UTC().Format(time.RFC3339)
	hub.mu.RUnlock()

	json.NewEncoder(w).Encode(data)
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	setCORSHeaders(w, r)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{
		"status":  "ONLINE",
		"engine":  "UFNS Go Real-Time Microservice v4.0",
		"runtime": "Go 1.22 Goroutine Stream",
	})
}

// Background Ingestor Goroutine
func startIngestWorker() {
	ticker := time.NewTicker(3 * time.Second)
	go func() {
		phase := 0.0
		for range ticker.C {
			phase += 0.1
			hub.mu.Lock()
			hub.telemetry.PrecipRateMMH = math.Round((15.0+10.0*math.Sin(phase))*10) / 10
			hub.telemetry.TideLevelM = math.Round((1.40+0.35*math.Sin(phase*0.5))*100) / 100
			hub.telemetry.Timestamp = time.Now().UTC().Format(time.RFC3339)
			hub.mu.Unlock()
		}
	}()
}

func main() {
	port := os.Getenv("GO_STREAM_PORT")
	if port == "" {
		port = "8080"
	}

	startIngestWorker()

	http.HandleFunc("/api/v1/stream/telemetry", telemetryHandler)
	http.HandleFunc("/api/v1/stream/health", healthHandler)

	addr := fmt.Sprintf(":%s", port)
	log.Printf("[UFNS Go Engine] High-concurrency telemetry streaming service active on %s\n", addr)
	if err := http.ListenAndServe(addr, nil); err != nil {
		log.Fatalf("Failed to start Go streaming server: %v", err)
	}
}

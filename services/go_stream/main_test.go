package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
)

func TestHealthHandler(t *testing.T) {
	req := httptest.NewRequest("GET", "/api/v1/stream/health", nil)
	w := httptest.NewRecorder()

	healthHandler(w, req)

	resp := w.Result()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected status 200, got %d", resp.StatusCode)
	}

	var data map[string]string
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if data["status"] != "ONLINE" {
		t.Errorf("expected status 'ONLINE', got '%s'", data["status"])
	}
}

func TestTelemetryHandler(t *testing.T) {
	req := httptest.NewRequest("GET", "/api/v1/stream/telemetry", nil)
	w := httptest.NewRecorder()

	telemetryHandler(w, req)

	resp := w.Result()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected status 200, got %d", resp.StatusCode)
	}

	var tel LiveTelemetry
	if err := json.NewDecoder(resp.Body).Decode(&tel); err != nil {
		t.Fatalf("failed to decode telemetry response: %v", err)
	}

	if tel.ActiveCity == "" {
		t.Errorf("expected non-empty ActiveCity, got empty string")
	}

	if tel.PrecipRateMMH < 0 {
		t.Errorf("precip rate must be non-negative, got %f", tel.PrecipRateMMH)
	}
}

func TestStreamHubConcurrency(t *testing.T) {
	var wg sync.WaitGroup
	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			hub.mu.Lock()
			hub.telemetry.PrecipRateMMH = float64(idx) * 1.5
			hub.mu.Unlock()

			hub.mu.RLock()
			_ = hub.telemetry.PrecipRateMMH
			hub.mu.RUnlock()
		}(i)
	}
	wg.Wait()
}

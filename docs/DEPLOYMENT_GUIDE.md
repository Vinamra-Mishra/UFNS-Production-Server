# UFNS Complete Hosting & Deployment Guide

**Target Platforms:** Vercel (Frontend), Render / Railway / Fly.io / AWS ECS (Backend), Docker Compose (Self-Hosted VPS)  
**Architecture Type:** Decoupled High-Performance Web Architecture (SPA on Global CDN + Containerized Polyglot Microservices)

---

## 1. Why Decoupled Hosting?

UFNS is composed of two distinct tiers:
1. **Frontend (`apps/web`)**: A high-performance React 18 + Vite SPA with Canvas 2D geospatial rendering. Ideal for **Vercel**, **Cloudflare Pages**, or **Netlify** because it is a static build that deploys to Edge CDNs with global $< 30\,\text{ms}$ Time-to-First-Byte (TTFB) and automatic SSL certificates.
2. **Backend (`apps/api`, `cpp_core`, `rust_core`, `services/go_stream`)**: A heavy computational server utilizing native C++20 OpenMP physics shared libraries (`libufns_physics`), EPA-SWMM hydrodynamic solvers, and persistent background WebSocket telemetry daemons. These require a **Linux container environment** (like Render, Railway, Fly.io, AWS, DigitalOcean, or Docker).

---

## 2. Option A: Deploying to Vercel (Frontend) + Render / Railway (Backend) — *Recommended (Free / Easy)*

### Step 1: Deploy Backend on Render (Free Tier)
1. Go to [render.com](https://render.com) and log in with your GitHub account (`Vinamra-Mishra`).
2. Click **New +** $\rightarrow$ **Web Service**.
3. Select the repository: `Vynex-Labs/UFNS-Demo-V4`.
4. Choose **Docker** as the Runtime (Render automatically detects the root [`Dockerfile`](../Dockerfile)).
5. Under Settings:
   - **Branch:** `main` or `final-demo`
   - **Health Check Path:** `/health`
6. Click **Create Web Service**.
7. Render will build the C++20 libraries and launch Uvicorn. Once deployed, note down your backend URL (e.g., `https://ufns-backend.onrender.com`).

*(Alternative: You can also deploy with one click on **Railway.app** or **Fly.io** using the same Dockerfile!)*

---

### Step 2: Deploy Frontend on Vercel
1. Go to [vercel.com](https://vercel.com) and log in with your GitHub account.
2. Click **Add New...** $\rightarrow$ **Project**.
3. Import the repository: `Vynex-Labs/UFNS-Demo-V4`.
4. In the Project Configuration:
   - **Framework Preset:** `Vite`
   - **Root Directory:** Click `Edit` and select `apps/web`
   - **Build Command:** `npm run build`
   - **Output Directory:** `dist`
5. **Configure Backend Proxy (`vercel.json`)**:
   - In [`apps/web/vercel.json`](../apps/web/vercel.json), replace the backend destination URL with your active Render/Railway backend URL (e.g., `https://ufns-backend.onrender.com`):
     ```json
     {
       "rewrites": [
         {
           "source": "/api/:path*",
           "destination": "https://ufns-backend.onrender.com/api/:path*"
         },
         {
           "source": "/health",
           "destination": "https://ufns-backend.onrender.com/health"
         },
         {
           "source": "/data/:path*",
           "destination": "https://ufns-backend.onrender.com/data/:path*"
         },
         {
           "source": "/(.*)",
           "destination": "/index.html"
         }
       ]
     }
     ```
6. Click **Deploy**. Vercel will build and assign your production URL (e.g., `https://ufns-demo-v4.vercel.app`).

---

## 3. Option B: One-Click Full Stack Deployment with Docker Compose (Cloud VPS)

If you have a Linux Cloud VM (AWS EC2, DigitalOcean Droplet, GCP Compute Engine, Hetzner):

1. Clone the repository on the server:
   ```bash
   git clone https://github.com/Vynex-Labs/UFNS-Demo-V4.git
   cd UFNS-Demo-V4
   ```

2. Start the full stack:
   ```bash
   docker compose up -d --build
   ```

3. The system will start:
   - **FastAPI + C++20 Backend:** Port `8000` (`http://your-server-ip:8000`)
   - **React 18 Dashboard:** Port `3000` (`http://your-server-ip:3000`)

---

## 4. Option C: Direct Vercel Monorepo Deployment

If you prefer deploying directly from the repository root without setting a subfolder:
1. In the root [`vercel.json`](../vercel.json), update the rewrite destinations to point to your live backend service URL.
2. Vercel automatically detects the root configuration, executes `npm --prefix apps/web run build`, and serves `apps/web/dist`.
3. Requests to `/api/*`, `/health`, and `/data/*` are transparently routed through Vercel Edge rewrites with full security headers (`X-Content-Type-Options`, `X-Frame-Options`).

---

## 5. Production Environment Checklist

* [x] **CORS Middleware & Allowlist:** Allowed origins in [`apps/api/app.py`](../apps/api/app.py), [`rust_api/src/main.rs`](../rust_api/src/main.rs), and [`services/go_stream/main.go`](../services/go_stream/main.go) restrict access to `http://localhost:3000`, `http://127.0.0.1:3000`, and `https://ufns-demo-v4.vercel.app` (additional deployment origins can be configured in their respective allowlist constants).
* [x] **Health Check Endpoint:** Active at `/health` returning status `"ok"` when all artifacts and providers are operational, or `"degraded"` when artifacts are missing or rainfall provider is unavailable.
* [x] **Fallback Data Providers:** Autonomous synthetic fallbacks ensure 100% uptime when external IMD/MOSDAC servers are unreachable.
* [x] **Single-Page Application (SPA) Routing:** `vercel.json` rewrites all client routes to `/index.html` preventing 404s on page refresh.
* [x] **Verified Cloud Deployment:** Production backend live on Render (`https://ufns-demo-v4.onrender.com`), reverse-proxied through Vercel frontend.

import { defineConfig } from '@playwright/test'
export default defineConfig({
 testDir:'./e2e', workers:1, timeout:30000,
 use:{baseURL:'http://127.0.0.1:8000',browserName:'chromium',trace:'retain-on-failure'},
 webServer:{command:'../.venv/bin/python ../tests/studio_e2e_server.py',url:'http://127.0.0.1:8000/api/health',reuseExistingServer:false,timeout:30000},
})

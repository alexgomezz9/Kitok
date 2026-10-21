import { defineConfig } from '@playwright/test'
const fixturePort=Number(process.env.KITOK_E2E_PORT||8000)
const fixtureURL=`http://127.0.0.1:${fixturePort}`
export default defineConfig({
 testDir:'./e2e', workers:1, timeout:30000,
 use:{baseURL:fixtureURL,browserName:'chromium',trace:'retain-on-failure'},
 webServer:{command:'../.venv/bin/python ../tests/studio_e2e_server.py',url:`${fixtureURL}/api/health`,reuseExistingServer:false,timeout:30000},
})

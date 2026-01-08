# QuickFIX/Python Market Data Client - NTPRO UAT

Production-ready FIX client for connecting to NTPRO UAT FIX API **Market Data session ONLY** with comprehensive logging.

## 🚀 Quick Start

You only need **Docker** installed. No Python or QuickFIX installation required!

### Start the FIX Client

```bash
docker-compose up --build
```

That's it! The application will:
- ✅ Connect to NTPRO UAT Market Data server
- ✅ Authenticate the session automatically
- ✅ Log all FIX messages sent and received
- ✅ Automatically reconnect if disconnected

### Stop the FIX Client

Press `Ctrl+C` or run:
```bash
docker-compose down
```

## 📋 Project Structure

```
test-AI/
├── main.py              # Main FIX client application - MARKET DATA ONLY
├── settings.cfg         # QuickFIX configuration (Market Data session)
├── Dockerfile           # Docker image configuration
├── docker-compose.yml   # Easy deployment configuration
├── requirements.txt     # Python dependencies (quickfix)
├── .dockerignore        # Files excluded from Docker build
├── log/                 # FIX session logs (created automatically)
└── store/               # FIX message store (created automatically)
```

## 🔧 Configuration Details

### Market Data Session

- SenderCompID: `SIRIUS_500007460_MD`
- TargetCompID: `NTPRO_IDBA_UAT`
- Host: `dsp-east-uat.ntprog.com`
- Port: `25421`
- Password: `Df2Hy8nM` (auto-injected)

### Connection Settings

- **Protocol**: FIX 4.4
- **SSL**: Disabled (direct connection)
- **HeartBeat**: 30 seconds
- **Reconnect Interval**: 30 seconds
- **Auto Reconnect**: Enabled

## 📊 Log Output

The application provides color-coded, comprehensive logging:

- **[SYSTEM]** - System events (startup, shutdown, status)
- **[SESSION]** - Session lifecycle (created, logon, logout)
- **[SEND →]** - Outgoing FIX messages
- **[RECV ←]** - Incoming FIX messages
- **[ADMIN]** - Administrative messages (Logon, Heartbeat, etc.)
- **[APP]** - Application messages (market data requests/responses)
- **[ERROR]** - Error conditions

### Example Output

```
[2026-01-07 11:00:00.123] [SESSION] MARKET_DATA              ✓ Session created: SIRIUS_500007460_MD → NTPRO_IDBA_UAT
[2026-01-07 11:00:00.234] [ADMIN  ] MARKET_DATA              🔑 Injected password into Logon message
[2026-01-07 11:00:00.345] [SEND   ] MARKET_DATA              → LOGON: 8=FIX.4.4 | 9=123 | 35=A | ...
[2026-01-07 11:00:01.456] [RECV   ] MARKET_DATA              ← LOGON: 8=FIX.4.4 | 9=98 | 35=A | ...
[2026-01-07 11:00:01.567] [SESSION] MARKET_DATA              ★ LOGGED ON ★ - Session active and ready!
```

## 📁 Log Files

Logs are written to two locations:

1. **Console**: Real-time color-coded output
2. **Files**: `./log/` directory
   - `FIX.4.4-SIRIUS_500007460_MD-NTPRO_IDBA_UAT.messages.current.log`
   - Event logs and session logs

## 🔍 Troubleshooting

### Connection Issues

1. **Check network connectivity:**
   ```bash
   ping dsp-east-uat.ntprog.com
   ```

2. **Verify port is accessible:**
   ```bash
   telnet dsp-east-uat.ntprog.com 25421
   ```

3. **Check Docker logs:**
   ```bash
   docker-compose logs -f
   ```

### Authentication Failures

- Verify credentials in `settings.cfg` are correct
- Check that password is being injected (look for "🔑 Injected password" in logs)
- Confirm SenderCompID and TargetCompID match server configuration

### Session Not Logging On

- Check QuickFIX logs in `./log/` directory
- Verify FIX version (should be FIX 4.4)
- Check sequence numbers (may need to reset: delete files in `./store/`)

### Reset Session

To reset sequence numbers and start fresh:

```bash
# Stop the container
docker-compose down

# Delete store files
rm -rf store/*
rm -rf log/*

# Restart
docker-compose up --build
```

## 🛠️ Development

### Run without Docker (if you have Python installed)

```bash
pip install -r requirements.txt
python main.py
```

### Modify Configuration

Edit `settings.cfg` to change:
- Connection parameters
- Session settings
- Logging levels
- Reconnect intervals

## 🔒 Security Note

⚠️ This configuration uses **unencrypted connections** (no SSL/TLS). Passwords are sent in plaintext. For production use, consider:
- Using SSL-enabled connections
- Restricting access by IP/subnet
- Using VPN or secure network

## 📝 License

This is a custom FIX client implementation for NTPRO UAT Market Data testing.


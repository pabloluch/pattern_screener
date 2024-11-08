# Crypto Wave Pattern Scanner

A real-time cryptocurrency pattern detection system that scans multiple timeframes for specific wave formations. Built with Python and FastAPI, deployed on Render.com.

## Features

- Real-time market data from MEXC Exchange
- Multi-timeframe analysis (1m to 3h)
- Custom wave indicator calculations
- Bull and bear pattern detection
- Interactive web dashboard
- Real-time WebSocket updates
- Pattern visualization with Chart.js
- Automatic scanning every 30 minutes

## Live Demo

Access the live scanner at: https://wave-pattern-scanner.onrender.com

## Technology Stack

- **Backend:**
  - FastAPI (Web framework)
  - WebSockets (Real-time updates)
  - aiohttp (Async HTTP requests)
  - numpy/pandas (Data processing)
  - Python 3.9+

- **Frontend:**
  - Chart.js (Wave visualization)
  - Moment.js (Time handling)
  - Pure JavaScript/HTML/CSS

- **Deployment:**
  - Render.com (Cloud platform)
  - Automatic deployment from GitHub

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/wave-pattern-scanner.git
cd wave-pattern-scanner
```

2. Create a virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
```

3. Run locally:
```bash
python main.py
```

## Project Structure

```
wave-pattern-scanner/
├── main.py                    # FastAPI application
├── market_data_fetcher.py     # MEXC API interface
├── timeframe_converter.py     # Timeframe handling
├── wave_indicator.py          # Wave calculations
├── combined_jttw_pattern.py   # Pattern detection
├── static/                    # Static files
│   └── index.html            # Dashboard interface
└── requirements.txt          # Python dependencies
```

## Features in Detail

### Pattern Detection
- Custom wave indicator based on EMAs
- Bull and Bear pattern identification
- Multiple timeframe support
- Position size consideration

### Real-time Dashboard
- Excel-like pattern display
- Interactive wave charts
- Pattern point visualization
- WebSocket-based updates
- Automatic refresh

### Supported Timeframes
- 1 minute to 3 hours
- Base timeframes: 1m, 5m, 15m, 60m
- Derived timeframes through conversion

## Configuration

No additional configuration needed. The application uses default MEXC API endpoints and public market data.

## Usage

1. Access the web interface
2. Patterns are automatically detected every 30 minutes
3. Click on pattern cells to view detailed wave charts
4. Pattern points are marked on the charts
5. Historical pattern snapshots are preserved

## Deployment

The application is configured for Render.com deployment:

1. Fork this repository
2. Create a new Web Service on Render
3. Connect your repository
4. Deploy

Render will automatically:
- Install dependencies
- Start the application
- Provide a public URL
- Handle SSL/HTTPS

## Limitations

- Render free tier has 750 hours/month runtime
- Some derived timeframes require base timeframe conversion
- Public API rate limits apply

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

MIT License - see LICENSE file for details.

## Acknowledgments

- MEXC Exchange for the market data API
- FastAPI for the web framework
- Chart.js for visualization capabilities
- Render.com for hosting

## Support

Create an issue in the repository for:
- Bug reports
- Feature requests
- Deployment questions
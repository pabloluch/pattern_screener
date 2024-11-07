# Crypto Wave Pattern Screener

A real-time cryptocurrency pattern detection system that scans multiple timeframes for specific wave patterns.

## Features

- Real-time market data fetching from MEXC Exchange
- Pattern detection across multiple timeframes
- WebSocket-based real-time updates
- Interactive web dashboard
- Automatic scanning every 30 minutes

## Setup & Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/wave-pattern-screener.git
cd wave-pattern-screener
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python main.py
```

## Wave Pattern Detection

The screener looks for specific wave patterns in both fast and slow waves:
- Bull patterns
- Bear patterns
- Multiple timeframe analysis
- Position size considerations

## Web Dashboard

Access the dashboard at the provided Render URL after deployment. Features include:
- Real-time pattern updates
- Pattern distribution visualization
- Detailed pattern information
- Historical pattern view

## Deployment

This application is configured for deployment on Render.com:

1. Fork this repository
2. Create a new Web Service on Render
3. Connect your forked repository
4. Deploy

## Configuration

The application can be configured through environment variables:
- `PORT`: Application port (default: 8000)
- Additional configuration can be done through the `render.yaml` file

## License

MIT License

## Acknowledgments

- MEXC Exchange for providing the market data API
- Technical analysis tools and libraries used in the project
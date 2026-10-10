# 🏀 Fantasy Basketball AI Assistant

> **Revolutionize your fantasy basketball experience with AI-powered insights that go beyond basic statistics**

An intelligent chatbot that connects directly to your Yahoo Fantasy Basketball league, providing personalized team analysis, trade recommendations, and strategic advice using advanced AI rather than traditional statistical tools.

## 🚀 What Makes This Different

Unlike conventional fantasy tools that rely purely on statistical analysis, this AI assistant:
- **Analyzes contextual data** - Understands matchups, player trends, and league dynamics
- **Provides conversational insights** - Chat naturally about your team like talking to an expert
- **Delivers personalized recommendations** - Tailored advice based on YOUR specific league and team
- **Processes real-time data** - Combines Yahoo Fantasy API with live NBA statistics

## ✨ Key Features

### 🤖 AI-Powered Chat Interface
- **Natural conversation** - Ask questions in plain English
- **Smart analysis** - AI processes your league data to provide contextual answers
- **Instant responses** - Get immediate insights about your team performance

### 📊 Comprehensive Team Analysis
- **Team optimization suggestions** - AI-driven lineup recommendations
- **Performance insights** - Deep analysis of player and team trends
- **Matchup predictions** - Strategic advice for weekly matchups
- **League comparison** - See how you stack up against competitors

### 🔄 Trade & Waiver Intelligence
- **Trade recommendations** - AI evaluates potential trades for maximum benefit
- **Waiver wire optimization** - Smart pickup suggestions based on your needs
- **Player value analysis** - Understand true player worth in your league context

### 🔗 Seamless Integration
- **Yahoo Fantasy connection** - Direct access to your league data
- **Real-time NBA stats** - Live player performance data
- **Secure authentication** - Google OAuth for easy, secure login

## 🛠 Tech Stack

- **Backend**: Python (Flask)
- **AI Engine**: LiteLLM (Gemini by default, any provider by config)
- **Database**: Firestore
- **Authentication**: Google OAuth + Yahoo Fantasy OAuth
- **APIs**: Yahoo Fantasy Sports API, NBA API
- **Frontend**: Web-based interface

## 📋 Prerequisites

- Python 3.8+
- Yahoo Fantasy Sports API credentials
- OpenAI API key
- Google OAuth credentials


## 💬 How to Use

### Getting Started
1. **Login** - Use your Google account for secure access
2. **Connect Yahoo** - Link your Yahoo Fantasy Sports account
3. **Select League** - Choose which fantasy league to analyze
4. **Start Chatting** - Ask the AI assistant anything about your team!

### Example Conversations
```
You: "How is my team performing this week?"
AI: "Your team is projected to win 7 out of 9 categories this week. 
     Your strongest categories are points and assists, but you're 
     weak in rebounds. Consider streaming a big man for tomorrow's games."

You: "Who should I pick up from the waiver wire?"
AI: "Based on your team's needs and upcoming schedules, I recommend 
     picking up [Player Name]. He has 4 games this week and fills 
     your biggest gap in three-point shooting."

You: "Should I accept this trade offer?"
AI: "That trade would improve your rebounds and blocks but hurt your 
     assists. Given your current league standing and team composition, 
     I'd suggest countering with [specific recommendation]."
```

## 📁 Project Structure

```
src/
├── appl/                    # Main Flask application
│   ├── app.py                # Application entry point
│   ├── routes/               # Route handlers
│   ├── services/             # Business logic
│   ├── middleware/           # Authentication decorators
│   └── config/               # Configuration files
├── firestore/                # User, Yahoo-link and league storage
│   ├── models/              # Data models
│   ├── repositories/        # Data access layer
│   └── services/            # Database services
├── database.py              # Database initialization
├── LeagueAnalyzer.py        # League analysis logic
├── PlayerAnalyzer.py        # Player statistics processing
├── TeamAnalyzer.py          # Team performance analysis
└── YahooLeague.py          # Yahoo API integration
```

## 🔐 Configuration

Create a `.env` file with the following variables:
```env
# LLM (via LiteLLM - swap provider by changing the model string)
LLM_MODEL=gemini/gemini-3.8-flash          # e.g. openai/gpt-4o-mini
EMBEDDING_MODEL=gemini/gemini-embedding-001
EMBEDDING_DIMENSIONS=768                    # must match the Firestore vector index
LLM_FALLBACK_MODEL=gemini/gemini-3.7-flash # optional: tried if the main model keeps failing
LLM_TIMEOUT_SECONDS=30                     # optional
GEMINI_API_KEY=your_gemini_api_key         # or OPENAI_API_KEY etc. for other providers

# Optional archive of synced league JSON (default: none). BLOB_STORAGE=gcs|azure|none
# GCS_BUCKET=your-bucket

# Retrieval vectors live in Firestore (uses Google application-default credentials)
GOOGLE_CLOUD_PROJECT=your_gcp_project_id
# One-time: create the vector index (dimension = EMBEDDING_DIMENSIONS)
#   gcloud firestore indexes composite create --collection-group=chunks #     --query-scope=COLLECTION #     --field-config=field-path=embedding,vector-config='{"dimension":"768","flat":"{}"}'


# Google OAuth
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret

# Flask Configuration
FLASK_SECRET_KEY=your_secret_key_here
```

## 🚀 Deployment

The application is ready for deployment and can be hosted on platforms like:
- **Heroku** - Easy deployment with hobby tier
- **Railway** - Modern deployment platform
- **DigitalOcean App Platform** - Scalable hosting
- **AWS/Google Cloud** - Enterprise-level deployment

## 🎯 Business Model

- **Target Users**: Fantasy basketball players seeking competitive advantage
- **Monetization**: Subscription-based service for premium AI insights
- **Value Proposition**: AI-powered analysis that goes beyond traditional statistics

## 🔮 Future Enhancements

- **Mobile app development**
- **Advanced ML models** for player performance prediction
- **Multi-league support** for managing multiple teams
- **Social features** for league member interaction
- **Historical analysis** and season-long trends
- **Custom AI training** on user preferences

## 🤝 Contributing

We welcome contributions! Please see our contributing guidelines for details on how to:
- Report bugs
- Suggest new features
- Submit pull requests
- Improve documentation

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📞 Support

Having issues or questions?
- **Documentation**: Check our [Wiki](wiki-link) for detailed guides
- **Issues**: Open a [GitHub issue](issues-link) for bug reports
- **Feature Requests**: Use our [feature request template](template-link)

## 🙏 Acknowledgments

- Yahoo Fantasy Sports API for providing league data access
- OpenAI for powering our intelligent analysis
- NBA API for real-time player statistics
- The fantasy basketball community for inspiration and feedback

---

**Ready to dominate your fantasy league with AI? [Get Started Now!](#quick-start)**


## 🧪 Tests
```
pytest                         # offline unit tests
FIRESTORE_TEST_PROJECT=<id> pytest -m integration   # Firestore contract tests
```

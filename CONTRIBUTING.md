# Contributing to EAN AgentOS

Thank you for your interest in contributing to EAN AgentOS! 🧠

## How to Contribute

### Reporting Bugs

1. Check [existing issues](https://github.com/eanai-ro/ean-agentos/issues) first
2. Create a new issue with:
   - Steps to reproduce
   - Expected vs actual behavior
   - Your environment (OS, Python version, CLI used)

### Suggesting Features

Open an issue with the `enhancement` label. Describe:
- The problem you're trying to solve
- Your proposed solution
- Why it benefits the community

### Submitting Code

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Run tests: `./test_full.sh`
5. Commit: `git commit -m "Add: description of change"`
6. Push: `git push origin feature/your-feature`
7. Open a Pull Request

### Code Guidelines

- Python 3.10+ compatible
- Follow existing code style (no strict linter, just be consistent)
- Add tests for new features
- Don't break existing tests (57 must pass)
- Keep it simple — avoid over-engineering

### What We're Looking For

- Bug fixes
- New CLI integrations (beyond Claude/Gemini/Codex/Kimi)
- Improved search/matching algorithms
- Better knowledge extraction patterns
- Documentation improvements
- Translations

### What's Out of Scope (Community Edition)

The following are part of EAN AgentOS Pro and not accepted as community contributions:
- Multi-agent orchestration
- AI deliberation
- CLI launcher
- Auto-pipeline
- Intelligence layer

## Development Setup

```bash
git clone https://github.com/eanai-ro/ean-agentos.git
cd ean-agentos
pip install flask flask-cors
python3 scripts/init_db.py
./test_full.sh  # Should pass 57/57
```

## Contact

- Email: ean@eanai.ro
- Issues: [GitHub Issues](https://github.com/eanai-ro/ean-agentos/issues)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

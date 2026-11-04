# WhatsGene

**BLAST for people who don't use BLAST every day.** Paste a sequence or accession and ask in plain words. You get a verified verdict with the exact E-value and identity and coverage behind it. It runs on your own machine and it support searching against your own local databases.

## Built at the Meta Global AI Developer Hackathon

WhatsGene was built for the [Meta Global AI Developer Hackathon](https://cerebralvalley.ai/e/meta-ai-developer-hackathon/details) by Cerebral Valley, track **Build for Your World**. All the code was written during the building period 27 Oct – 4 Nov 2026. The first commit is dated 29 Oct 2026.

Meta models used most:

- `muse-spark-1.3-contributer`
- `muse-wonder-1.0`

The major features of this app is **Muse explains, code computes.** Muse reads your question and writes the verdict. Code picks the search and runs BLAST engine to  judge each hit and checks every number Muse writes.

## Run it

```bash
git clone https://github.com/JUNXUN11/WhatsGene.git ~/WhatsGene && cd ~/WhatsGene && ./start
```

You need macOS or Linux, Git, Python 3.12+, Node 20+, and BLAST+ (`brew install blast`). When the browser opens, create your account. Then press **Run setup now** in Settings to build the database, and try `P68871` with the question "Identify this protein".

To turn on Muse, paste your API key in Settings → Muse AI. Without a key everything still works with answers written by code.

## Docs

WhatsGene was built waterfall-style: requirements, then rules, design, plan, build and deploy. Every change after sign-off is logged in the PRD. Start at [docs/](docs/README.md).

- [PRD](docs/PRD.md): requirements baseline and the changes made after sign-off
- [BLAST rules](docs/blast-rules.md): the science the code follows
- [Architecture](docs/ARCHITECTURE.md): the system as built
- [Roadmap](docs/ROADMAP.md): planned vs delivered

## License

MIT, see [LICENSE](LICENSE). WhatsGene is for research and education. It does not give medical advice.

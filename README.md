# PubMed MCP Server

[![smithery badge](https://smithery.ai/badge/@t0mst0ne/pubmed-mcp-easy)](https://smithery.ai/server/@t0mst0ne/pubmed-mcp-easy)

Enhanced Python-based PubMed MCP Server with API key support for faster and unlimited downloads.

## Certified by MCP Review at [https://mcpreview.com/mcp-servers/t0mst0ne/pubmed-mcp-easy]

## Features

- Search PubMed for biomedical literature and research papers
- Find similar articles, cited articles, and citing articles
- Retrieve abstracts and full text of open access articles
- Batch search and advanced search capabilities
- API key support for faster and unlimited downloads

## API Key and Email Setup

The NCBI E-utilities API recommends using an API key and email address with your requests. This brings several benefits:

- **Higher rate limits**: 10 requests/second instead of 3
- **More results per query**: Up to 200 results per request instead of 100
- **Priority service**: Better queue position for your requests

### How to Get an API Key

1. Create an NCBI account at [https://www.ncbi.nlm.nih.gov/account/](https://www.ncbi.nlm.nih.gov/account/)
2. Go to the API Keys Management page
3. Generate a new API key

### Setting Up API Key and Email

The easiest way to set up your API key and email is using the setup script:

```bash
python setup_api.py
```

This interactive script will guide you through the process and offer multiple setup options.

Alternatively, you can set up your API key and email manually using one of these three methods:

#### 1. Environment Variables

```bash
export NCBI_API_KEY=your_api_key_here
export NCBI_EMAIL=your_email@example.com
```

#### 2. Command Line Arguments

```bash
python python-pubmed-mcp-enhanced.py --api-key your_api_key_here --email your_email@example.com
```

#### 3. Configuration File

Create a `config.json` file based on the example:

```bash
cp config.json.example config.json
```

Edit `config.json` to include your API key and email:

```json
{
  "api_key": "your_api_key_here",
  "email": "your_email@example.com"
}
```

Then run the server with the config file:

```bash
python python-pubmed-mcp-enhanced.py --config config.json
```

## Usage

### Installing via Smithery

To install pubmed-mcp-easy for Claude Desktop automatically via [Smithery](https://smithery.ai/server/@t0mst0ne/pubmed-mcp-easy):

```bash
npx -y @smithery/cli install @t0mst0ne/pubmed-mcp-easy --client claude
```

### Standard Usage

Run the server:

```bash
python python-pubmed-mcp-enhanced.py
```

### Claude Desktop Integration

To integrate with Claude Desktop, add the following to your `claude_desktop_config.json` file:

```json
"pubmed-easy": {
    "command": "/opt/anaconda3/bin/python",
    "args": [
        "/GITHUB_cloned_dir/pubmed-mcp-easy/python-pubmed-mcp-enhanced.py", "--config", "config.json"
    ]
}
```

Make sure to:
1. Replace `/opt/anaconda3/bin/python` with the path to your Python executable
2. Replace `/GITHUB_cloned_dir` with the actual path to your GitHub directory
3. Create a `config.json` file with your API key and email as described above

After adding this configuration, you can access PubMed tools directly from Claude Desktop.

### Available Tools

The server provides the following MCP tools:

- `pubmed_search`: Search for articles by keyword or query
- `pubmed_similar`: Find similar articles
- `pubmed_cites`: Find articles cited by a specific paper
- `pubmed_cited_by`: Find articles that cite a specific paper
- `pubmed_abstract`: Retrieve the abstract of an article
- `pubmed_open_access`: Check if an article is open access
- `pubmed_full_text`: Retrieve the full text of an open access article
- `pubmed_batch_search`: Perform multiple searches in parallel
- `pubmed_author_search`: Search for papers by a specific author
- `pubmed_advanced_search`: Perform advanced field-based searches
- `pubmed_journal_search`: Search for papers in a specific journal

## Important Notes

1. Including an email address is recommended by NCBI as it allows them to contact you if there are issues with your requests.
2. If you make heavy use of the E-utilities, NCBI recommends that you limit large jobs to either weekends or between 9 pm and 5 am Eastern Time weekdays.
3. Always be considerate in your usage and follow NCBI's usage guidelines.

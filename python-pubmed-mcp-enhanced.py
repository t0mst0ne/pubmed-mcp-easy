#!/usr/bin/env python3
"""
Enhanced Python-based PubMed MCP Server with API key support.
This version provides faster and unlimited downloads by utilizing the NCBI E-utilities API key.
"""

import asyncio
import json
import logging
import os
import sys
import argparse
from typing import Dict, List, Optional, Any, Union
import aiohttp
from pydantic import BaseModel, Field, validator
from mcp.server.fastmcp import FastMCP

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger("pubmed-mcp")

# Initialize MCP server
mcp = FastMCP("pubmed-mcp")

# Define constants
BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PUBMED_URL = "https://pubmed.ncbi.nlm.nih.gov"
PMC_URL = "https://www.ncbi.nlm.nih.gov/pmc/articles"

# API Key and Email configuration
# Can be set via environment variables or command line arguments
# Environment variables: NCBI_API_KEY and NCBI_EMAIL
# Command line: --api-key and --email
API_KEY = os.environ.get("NCBI_API_KEY", "")
EMAIL = os.environ.get("NCBI_EMAIL", "")

# With API key, you can make up to 10 requests per second instead of 3
# And up to 300 requests instead of 100 per IP address before getting blocked
API_REQUESTS_PER_SECOND = 10 if API_KEY else 3
API_RATE_LIMITER = asyncio.Semaphore(API_REQUESTS_PER_SECOND)

# Global HTTP session
session = None

# Define data models
class PubmedPaper(BaseModel):
    """Model for a PubMed paper."""
    title: str
    authors: str
    pubDate: str
    pmid: int
    pmc: Optional[int] = None
    doi: Optional[str] = None
    journal: Optional[str] = None  # Added journal information

class PubmedSearchResult(BaseModel):
    """Model for PubMed search results."""
    count: int
    papers: List[PubmedPaper]

# Helper functions
async def get_session() -> aiohttp.ClientSession:
    """Get or create the global HTTP session."""
    global session
    if session is None or session.closed:
        timeout = aiohttp.ClientTimeout(total=30)
        session = aiohttp.ClientSession(timeout=timeout)
    return session

async def close_session() -> None:
    """Close the global HTTP session."""
    global session
    if session and not session.closed:
        await session.close()
        session = None

async def fetch_with_retry(url: str, params: Dict, max_retries: int = 3) -> Any:
    """Fetch data from URL with retry logic and rate limiting."""
    session = await get_session()
    retry_count = 0
    backoff = 1
    
    # Add API key and email to parameters if available
    if API_KEY:
        params["api_key"] = API_KEY
    if EMAIL:
        params["email"] = EMAIL
    
    async with API_RATE_LIMITER:
        while retry_count < max_retries:
            try:
                async with session.get(url, params=params) as response:
                    response.raise_for_status()
                    content_type = response.headers.get("Content-Type", "")
                    
                    if "application/json" in content_type:
                        return await response.json()
                    elif "text/xml" in content_type or "application/xml" in content_type:
                        return await response.text()
                    else:
                        return await response.read()
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                retry_count += 1
                if retry_count >= max_retries:
                    raise
                logger.warning(f"Request failed, retrying ({retry_count}/{max_retries}): {str(e)}")
                await asyncio.sleep(backoff)
                backoff *= 2

def extract_pubmed_papers(data: Dict) -> List[PubmedPaper]:
    """Extract PubMed papers from API response."""
    papers = []
    if "esearchresult" not in data or "idlist" not in data["esearchresult"]:
        return papers
    
    pmids = data["esearchresult"]["idlist"]
    return papers

async def fetch_paper_details(pmids: List[str]) -> List[PubmedPaper]:
    """Fetch details for a list of PubMed IDs."""
    if not pmids:
        return []
    
    # For better performance, split large batches of PMIDs into smaller chunks
    batch_size = 200  # Increased from typical 50 to 200 with API key
    papers = []
    
    for i in range(0, len(pmids), batch_size):
        batch_pmids = pmids[i:i+batch_size]
        
        # Fetch summary data for the PMIDs
        summary_url = f"{BASE_URL}/esummary.fcgi"
        summary_params = {
            "db": "pubmed",
            "id": ",".join(batch_pmids),
            "retmode": "json"
        }
        
        summary_data = await fetch_with_retry(summary_url, summary_params)
        
        for pmid in batch_pmids:
            if pmid in summary_data.get("result", {}) and pmid != "uids":
                article = summary_data["result"][pmid]
                
                # Extract authors
                authors = []
                for author in article.get("authors", []):
                    if author.get("authtype") == "Author" and "name" in author:
                        authors.append(author["name"])
                
                authors_str = ", ".join(authors[:5])  # Limit to first 5 authors for brevity
                if len(authors) > 5:
                    authors_str += f" et al. ({len(authors) - 5} more)"
                
                # Extract DOI
                doi = None
                articleids = article.get("articleids", [])
                for id_obj in articleids:
                    if id_obj.get("idtype") == "doi":
                        doi = id_obj.get("value")
                        break
                
                # Extract PMC ID
                pmc = None
                for id_obj in articleids:
                    if id_obj.get("idtype") == "pmc":
                        pmc_value = id_obj.get("value", "")
                        if pmc_value.startswith("PMC"):
                            try:
                                pmc = int(pmc_value[3:])
                            except ValueError:
                                pass
                        break
                
                paper = PubmedPaper(
                    title=article.get("title", "N/A"),
                    authors=authors_str or "N/A",
                    pubDate=article.get("pubdate", "N/A"),
                    pmid=int(pmid),
                    pmc=pmc,
                    doi=doi,
                    journal=article.get("fulljournalname", article.get("source", "N/A"))
                )
                papers.append(paper)
    
    return papers

async def fetch_papers_in_batches(func_name: str, ids: List[int], batch_size: int = 100) -> List[Any]:
    """Fetch papers in batches to avoid overloading the API."""
    results = []
    for i in range(0, len(ids), batch_size):
        batch = ids[i:i+batch_size]
        tasks = [globals()[func_name](id) for id in batch]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in batch_results:
            if isinstance(result, dict) and result.get("success") and "data" in result:
                results.extend(result["data"] if isinstance(result["data"], list) else [result["data"]])
    
    return results

# MCP Tool implementations
@mcp.tool()
async def pubmed_search(query: str, page: Optional[int] = None, limit: Optional[int] = None) -> Dict:
    """
    Searches PubMed for biomedical literature and research papers. Best for queries related to 
    medical research, clinical studies, scientific publications, and health topics. Returns information 
    including: titles, authors, publication dates, PMIDs, PMCs, and DOIs. Use this when the query 
    is related to medical or scientific research. Results are sorted by relevance to the search query.
    """
    try:
        # Default values
        page = max(1, page or 1)
        limit = max(1, min(200 if API_KEY else 100, limit or 10))  # Default 10, max 100/200
        
        # Calculate retstart parameter
        retstart = (page - 1) * limit
        
        # Search for PMIDs
        search_url = f"{BASE_URL}/esearch.fcgi"
        search_params = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": limit,
            "retstart": retstart,
            "sort": "relevance",  # Sort by relevance
            "usehistory": "y"     # Use WebEnv and QueryKey for faster subsequent requests
        }
        
        search_data = await fetch_with_retry(search_url, search_params)
        
        if "esearchresult" not in search_data:
            return {"success": False, "error": "Invalid response from PubMed"}
        
        # Get total count and PMIDs
        count = int(search_data["esearchresult"].get("count", 0))
        pmids = search_data["esearchresult"].get("idlist", [])
        
        # Fetch paper details
        papers = await fetch_paper_details(pmids)
        
        # Return formatted results
        result = PubmedSearchResult(count=count, papers=papers)
        return {"success": True, "data": json.loads(result.model_dump_json())}
        
    except Exception as e:
        logger.error(f"Error in pubmed_search: {str(e)}")
        return {"success": False, "error": str(e)}

@mcp.tool()
async def pubmed_similar(pmid: int) -> Dict:
    """
    Finds similar articles to a specific PubMed article based on its PMID. 
    Best for finding related articles to a specific paper. Returns information 
    including: titles, authors, publication dates, PMIDs, PMCs, and DOIs.
    """
    try:
        # Use elink to find similar articles
        elink_url = f"{BASE_URL}/elink.fcgi"
        elink_params = {
            "db": "pubmed",
            "cmd": "neighbor_score",
            "id": pmid,
            "retmode": "json",
            "linkname": "pubmed_pubmed",  # Explicitly specify linkname for similar articles
            "retmax": 100  # Get more similar articles
        }
        
        elink_data = await fetch_with_retry(elink_url, elink_params)
        
        # Extract similar article PMIDs
        similar_pmids = []
        try:
            link_sets = elink_data.get("linksets", [])
            if link_sets and "linksetdbs" in link_sets[0]:
                for linkset in link_sets[0]["linksetdbs"]:
                    if linkset.get("linkname") == "pubmed_pubmed":
                        similar_pmids = [str(pid) for pid in linkset.get("links", [])]
                        break
        except (KeyError, IndexError) as e:
            logger.warning(f"Error extracting similar PMIDs: {str(e)}")
        
        # Fetch paper details
        papers = await fetch_paper_details(similar_pmids)
        
        return {"success": True, "data": [json.loads(paper.model_dump_json()) for paper in papers]}
        
    except Exception as e:
        logger.error(f"Error in pubmed_similar: {str(e)}")
        return {"success": False, "error": str(e)}

@mcp.tool()
async def pubmed_cites(pmid: int) -> Dict:
    """
    Finds articles that a specific PubMed article cites based on its PMID. 
    Best for finding articles that a specific paper cites. Returns information 
    including: titles, authors, publication dates, PMIDs, PMCs, and DOIs.
    """
    try:
        # Use elink to find cited articles
        elink_url = f"{BASE_URL}/elink.fcgi"
        elink_params = {
            "db": "pubmed",
            "cmd": "neighbor_history",
            "id": pmid,
            "linkname": "pubmed_pubmed_refs",
            "retmode": "json"
        }
        
        elink_data = await fetch_with_retry(elink_url, elink_params)
        
        # Get the WebEnv and QueryKey
        try:
            link_sets = elink_data.get("linksets", [])
            web_env = link_sets[0].get("webenv", "")
            query_key = link_sets[0].get("linksetdbhistory", [{}])[0].get("querykey", "")
        except (KeyError, IndexError):
            return {"success": True, "data": []}
        
        if not web_env or not query_key:
            return {"success": True, "data": []}
        
        # Use the WebEnv and QueryKey to fetch the cited articles
        search_url = f"{BASE_URL}/esearch.fcgi"
        search_params = {
            "db": "pubmed",
            "term": "",
            "WebEnv": web_env,
            "query_key": query_key,
            "retmode": "json",
            "retmax": 200 if API_KEY else 100  # Increased limit with API key
        }
        
        search_data = await fetch_with_retry(search_url, search_params)
        
        cited_pmids = search_data.get("esearchresult", {}).get("idlist", [])
        
        # Fetch paper details
        papers = await fetch_paper_details(cited_pmids)
        
        return {"success": True, "data": [json.loads(paper.model_dump_json()) for paper in papers]}
        
    except Exception as e:
        logger.error(f"Error in pubmed_cites: {str(e)}")
        return {"success": False, "error": str(e)}

@mcp.tool()
async def pubmed_cited_by(pmid: int) -> Dict:
    """
    Finds articles that cite a specific PubMed article based on its PMID. 
    Best for finding articles that have cited a specific paper. Returns information 
    including: titles, authors, publication dates, PMIDs, PMCs, and DOIs.
    """
    try:
        # Use elink to find articles that cite this article
        elink_url = f"{BASE_URL}/elink.fcgi"
        elink_params = {
            "db": "pubmed",
            "cmd": "neighbor_history",
            "id": pmid,
            "linkname": "pubmed_pubmed_citedin",
            "retmode": "json"
        }
        
        elink_data = await fetch_with_retry(elink_url, elink_params)
        
        # Get the WebEnv and QueryKey
        try:
            link_sets = elink_data.get("linksets", [])
            web_env = link_sets[0].get("webenv", "")
            query_key = link_sets[0].get("linksetdbhistory", [{}])[0].get("querykey", "")
        except (KeyError, IndexError):
            return {"success": True, "data": []}
        
        if not web_env or not query_key:
            return {"success": True, "data": []}
        
        # Use the WebEnv and QueryKey to fetch the citing articles
        search_url = f"{BASE_URL}/esearch.fcgi"
        search_params = {
            "db": "pubmed",
            "term": "",
            "WebEnv": web_env,
            "query_key": query_key,
            "retmode": "json",
            "retmax": 200 if API_KEY else 100  # Increased limit with API key
        }
        
        search_data = await fetch_with_retry(search_url, search_params)
        
        citing_pmids = search_data.get("esearchresult", {}).get("idlist", [])
        
        # Fetch paper details
        papers = await fetch_paper_details(citing_pmids)
        
        return {"success": True, "data": [json.loads(paper.model_dump_json()) for paper in papers]}
        
    except Exception as e:
        logger.error(f"Error in pubmed_cited_by: {str(e)}")
        return {"success": False, "error": str(e)}

@mcp.tool()
async def pubmed_abstract(pmid: int) -> Dict:
    """
    Retrieves the abstract text of a specific PubMed article based on its PMID. 
    Returns only the abstract text.
    """
    try:
        # Use efetch to get the abstract
        efetch_url = f"{BASE_URL}/efetch.fcgi"
        efetch_params = {
            "db": "pubmed",
            "id": pmid,
            "retmode": "xml",
            "rettype": "abstract"
        }
        
        xml_content = await fetch_with_retry(efetch_url, efetch_params)
        
        # Extract abstract from XML
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml_content)
            
            # Look for abstract sections
            abstract_sections = root.findall(".//Abstract/AbstractText")
            if abstract_sections:
                abstract_parts = []
                for section in abstract_sections:
                    label = section.get("Label", "")
                    text = section.text or ""
                    if label:
                        abstract_parts.append(f"{label}: {text}")
                    else:
                        abstract_parts.append(text)
                abstract = " ".join(abstract_parts)
            else:
                abstract = root.findtext(".//Abstract/AbstractText", default="")
            
            return {"success": True, "data": abstract or "No abstract available"}
            
        except ET.ParseError:
            return {"success": False, "error": "Failed to parse XML response"}
            
    except Exception as e:
        logger.error(f"Error in pubmed_abstract: {str(e)}")
        return {"success": False, "error": str(e)}

@mcp.tool()
async def pubmed_open_access(pmid: int) -> Dict:
    """
    Checks if a specific PubMed article is open access based on its PMID. 
    Returns true if the article is open access, false otherwise.
    """
    try:
        # Use elink to check for PMC links
        elink_url = f"{BASE_URL}/elink.fcgi"
        elink_params = {
            "db": "pubmed",
            "dbfrom": "pubmed",
            "cmd": "llinks",
            "id": pmid,
            "retmode": "json"
        }
        
        elink_data = await fetch_with_retry(elink_url, elink_params)
        
        # Check for PMC links
        has_pmc = False
        try:
            link_sets = elink_data.get("linksets", [])
            for link_set in link_sets:
                for id_urls in link_set.get("idurls", []):
                    if "pmc/articles" in id_urls.get("url", "").lower():
                        has_pmc = True
                        break
        except (KeyError, IndexError):
            pass
        
        return {"success": True, "data": has_pmc}
        
    except Exception as e:
        logger.error(f"Error in pubmed_open_access: {str(e)}")
        return {"success": False, "error": str(e)}

@mcp.tool()
async def pubmed_full_text(pmid: int) -> Dict:
    """
    Retrieves the full text of an open access PubMed article based on its PMID. 
    Please check if a PMID is open access before using this tool.
    """
    try:
        # First check if it's open access
        is_oa_result = await pubmed_open_access(pmid)
        if not is_oa_result.get("success", False) or not is_oa_result.get("data", False):
            return {"success": False, "error": "This article is not open access or not available in PMC"}
        
        # Get the PMC ID for this PMID
        summary_url = f"{BASE_URL}/esummary.fcgi"
        summary_params = {
            "db": "pubmed",
            "id": pmid,
            "retmode": "json"
        }
        
        summary_data = await fetch_with_retry(summary_url, summary_params)
        
        pmc_id = None
        try:
            article = summary_data["result"][str(pmid)]
            articleids = article.get("articleids", [])
            for id_obj in articleids:
                if id_obj.get("idtype") == "pmc":
                    pmc_value = id_obj.get("value", "")
                    if pmc_value.startswith("PMC"):
                        pmc_id = pmc_value
                    break
        except (KeyError, TypeError):
            return {"success": False, "error": "Failed to find PMC ID for this article"}
        
        if not pmc_id:
            return {"success": False, "error": "No PMC ID found for this article"}
        
        # Use efetch to get the full text from PMC
        efetch_url = f"{BASE_URL}/efetch.fcgi"
        efetch_params = {
            "db": "pmc",
            "id": pmc_id,
            "retmode": "xml",
            "rettype": "full"
        }
        
        xml_content = await fetch_with_retry(efetch_url, efetch_params)
        
        # Extract the article text
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml_content)
            
            # Get the article body text
            body = root.find(".//body")
            if body is None:
                return {"success": False, "error": "Full text structure not found in PMC"}
            
            # Extract text from all paragraphs
            paragraphs = []
            for p in body.findall(".//p"):
                if p.text:
                    paragraphs.append(p.text.strip())
            
            if not paragraphs:
                return {"success": False, "error": "No paragraphs found in the full text"}
            
            full_text = "\n\n".join(paragraphs)
            return {"success": True, "data": full_text}
            
        except ET.ParseError:
            return {"success": False, "error": "Failed to parse XML full text"}
            
    except Exception as e:
        logger.error(f"Error in pubmed_full_text: {str(e)}")
        return {"success": False, "error": str(e)}

@mcp.tool()
async def pubmed_batch_search(queries: List[str], limit: Optional[int] = None) -> Dict:
    """
    Performs multiple PubMed searches in parallel for efficient batch processing.
    Returns results for each query in the same order as the input queries.
    """
    try:
        limit = max(1, min(200 if API_KEY else 100, limit or 10))
        
        # Create a task for each query
        tasks = [pubmed_search(query, 1, limit) for query in queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        batch_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                batch_results.append({
                    "query": queries[i],
                    "success": False,
                    "error": str(result),
                    "data": None
                })
            else:
                batch_results.append({
                    "query": queries[i],
                    "success": result.get("success", False),
                    "error": result.get("error", None),
                    "data": result.get("data", None)
                })
        
        return {"success": True, "data": batch_results}
        
    except Exception as e:
        logger.error(f"Error in pubmed_batch_search: {str(e)}")
        return {"success": False, "error": str(e)}

@mcp.tool()
async def pubmed_author_search(author: str, limit: Optional[int] = None) -> Dict:
    """
    Searches for papers by a specific author.
    The author name should be in the format "Last Name, First Initial" (e.g., "Smith, J")
    """
    try:
        # Format author name for search
        formatted_author = f"{author}[Author]"
        return await pubmed_search(formatted_author, 1, limit)
        
    except Exception as e:
        logger.error(f"Error in pubmed_author_search: {str(e)}")
        return {"success": False, "error": str(e)}

@mcp.tool()
async def pubmed_advanced_search(params: Dict[str, str], limit: Optional[int] = None) -> Dict:
    """
    Performs an advanced PubMed search using field tags.
    
    Example params:
    {
        "author": "Smith J",
        "journal": "Nature",
        "year": "2020",
        "title": "cancer",
        "mesh": "Drug Therapy"
    }
    """
    try:
        # Build advanced query
        query_parts = []
        
        field_mappings = {
            "author": "[Author]",
            "journal": "[Journal]",
            "year": "[Publication Date]",
            "title": "[Title]",
            "mesh": "[MeSH Terms]",
            "affiliation": "[Affiliation]",
            "doi": "[DOI]",
            "keyword": "[Keyword]"
        }
        
        for field, value in params.items():
            if field in field_mappings:
                query_parts.append(f"{value}{field_mappings[field]}")
            else:
                query_parts.append(value)
        
        query = " AND ".join(query_parts)
        return await pubmed_search(query, 1, limit)
        
    except Exception as e:
        logger.error(f"Error in pubmed_advanced_search: {str(e)}")
        return {"success": False, "error": str(e)}

@mcp.tool()
async def pubmed_journal_search(journal: str, limit: Optional[int] = None) -> Dict:
    """
    Searches for papers published in a specific journal.
    """
    try:
        journal_query = f"{journal}[Journal]"
        return await pubmed_search(journal_query, 1, limit)
        
    except Exception as e:
        logger.error(f"Error in pubmed_journal_search: {str(e)}")
        return {"success": False, "error": str(e)}

def parse_arguments():
    """Parse command line arguments for API key and email."""
    parser = argparse.ArgumentParser(description="Enhanced PubMed MCP Server with API support")
    parser.add_argument("--api-key", type=str, help="NCBI API key for faster and unlimited downloads")
    parser.add_argument("--email", type=str, help="Email address to include with NCBI API requests")
    parser.add_argument("--port", type=int, default=3000, help="Port to run the MCP server on")
    parser.add_argument("--config", type=str, help="Path to configuration file")
    return parser.parse_args()

def load_config(config_path):
    """Load configuration from file."""
    if not config_path or not os.path.exists(config_path):
        return {}
        
    try:
        with open(config_path, 'r') as f:
            import json
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading config file: {str(e)}")
        return {}

if __name__ == "__main__":
    # Parse command line arguments
    args = parse_arguments()
    
    # Load config file if specified
    config = load_config(args.config)
    
    # Override with command line arguments (highest priority)
    if args.api_key:
        API_KEY = args.api_key
    elif config.get("api_key"):
        API_KEY = config.get("api_key")
        
    if args.email:
        EMAIL = args.email
    elif config.get("email"):
        EMAIL = config.get("email")
    
    # Display API key and email status
    if API_KEY:
        logger.info(f"PubMed API Key detected: Using enhanced limits (10 req/sec, 200 results max)")
    else:
        logger.info(f"No PubMed API Key found: Using standard limits (3 req/sec, 100 results max)")
        logger.info(f"Set NCBI_API_KEY environment variable or use --api-key for faster downloads")
        
    if EMAIL:
        logger.info(f"Email address set for PubMed requests: {EMAIL}")
    else:
        logger.info(f"No email address set for PubMed requests (recommended but not required)")
    
    try:
        # The FastMCP implementation doesn't have an async run method
        # We'll use the synchronous run method instead
        mcp.run()
    except KeyboardInterrupt:
        logger.info("Server interrupted, shutting down...")
    finally:
        # Create a loop to run the session cleanup
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(close_session())
        finally:
            loop.close()

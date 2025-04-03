#!/usr/bin/env python3
"""
Python-based PubMed MCP Server.
Similar to the Node.js implementation but using Python libraries.
"""

import asyncio
import json
import logging
import sys
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
    """Fetch data from URL with retry logic."""
    session = await get_session()
    retry_count = 0
    backoff = 1
    
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
    
    # Fetch summary data for the PMIDs
    summary_url = f"{BASE_URL}/esummary.fcgi"
    summary_params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json"
    }
    
    summary_data = await fetch_with_retry(summary_url, summary_params)
    
    papers = []
    for pmid in pmids:
        if pmid in summary_data.get("result", {}) and pmid != "uids":
            article = summary_data["result"][pmid]
            
            # Extract authors
            authors = []
            for author in article.get("authors", []):
                if author.get("authtype") == "Author" and "name" in author:
                    authors.append(author["name"])
            
            authors_str = ", ".join(authors) if authors else "N/A"
            
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
                authors=authors_str,
                pubDate=article.get("pubdate", "N/A"),
                pmid=int(pmid),
                pmc=pmc,
                doi=doi
            )
            papers.append(paper)
    
    return papers

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
        limit = max(1, min(100, limit or 10))  # Default 10, max 100
        
        # Calculate retstart parameter
        retstart = (page - 1) * limit
        
        # Search for PMIDs
        search_url = f"{BASE_URL}/esearch.fcgi"
        search_params = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": limit,
            "retstart": retstart
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
        return {"success": True, "data": json.loads(result.json())}
        
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
            "retmode": "json"
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
        
        return {"success": True, "data": [json.loads(paper.json()) for paper in papers]}
        
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
            "retmax": 100
        }
        
        search_data = await fetch_with_retry(search_url, search_params)
        
        cited_pmids = search_data.get("esearchresult", {}).get("idlist", [])
        
        # Fetch paper details
        papers = await fetch_paper_details(cited_pmids)
        
        return {"success": True, "data": [json.loads(paper.json()) for paper in papers]}
        
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
            "retmax": 100
        }
        
        search_data = await fetch_with_retry(search_url, search_params)
        
        citing_pmids = search_data.get("esearchresult", {}).get("idlist", [])
        
        # Fetch paper details
        papers = await fetch_paper_details(citing_pmids)
        
        return {"success": True, "data": [json.loads(paper.json()) for paper in papers]}
        
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

if __name__ == "__main__":
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

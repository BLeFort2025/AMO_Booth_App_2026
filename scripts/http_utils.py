import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def get_robust_session() -> requests.Session:
    """
    Returns a requests.Session configured with exponential backoff retries.
    It will retry on connection errors and specific HTTP status codes.
    """
    session = requests.Session()
    
    # Retry strategy:
    # 5 total retries
    # Backoff factor 1.0 means sleep times will be: 1.0, 2.0, 4.0, 8.0 seconds
    retry_strategy = Retry(
        total=5,
        status_forcelist=[429, 500, 502, 503, 504],
        backoff_factor=1.0,
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # Disable verify warnings globally since we connect to statcan
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    return session

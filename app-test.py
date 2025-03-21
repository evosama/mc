from fastapi import FastAPI, BackgroundTasks, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
import httpx
import asyncio
import logging
import datetime
import base64
import os
import glob

# FastAPI app and templates setup
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/reports", StaticFiles(directory="reports"), name="reports")
templates = Jinja2Templates(directory="templates")

# Load environment variables from .env file
project_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = project_dir + "\\api_keys.env"
load_dotenv(dotenv_path)
reports_dir = os.path.join(project_dir, "reports")

ninja_client_id = os.getenv('NINJA_CLIENT_ID')
ninja_client_secret = os.getenv('NINJA_CLIENT_SECRET')
bd_api_key = os.getenv('BD_API_KEY')
bd_id = os.getenv('BD_ID')

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

NINJA_API_BASE_URL = "https://app.ninjarmm.com/api/v2"
BITDEFENDER_API_URL = "https://cloud.gravityzone.bitdefender.com/api/v1.0/jsonrpc/network"

class ReportGenerator:
    def __init__(self, ninja_client_id, ninja_client_secret, bd_api_key, bd_id):
        # Ensure credentials are valid
        if not all([ninja_client_id, ninja_client_secret, bd_api_key, bd_id]):
            raise ValueError("All API credentials must be provided.")

        # Credentials
        self.ninja_client_id = ninja_client_id
        self.ninja_client_secret = ninja_client_secret
        self.bd_api_key = bd_api_key
        self.bd_id = bd_id

        # Data variables
        self.progress_lock = asyncio.Lock()
        # self.progress = {"Stage": "", "Company": "", "Percent": 0}
        self.progress = {"percent": 0}  # Initialize progress at 0%

        # HTML report placeholders
        self.ninja_html_report = ""
        self.bd_html_report = ""

    async def get_ninja_access_token(self):
        token_url = "https://app.ninjarmm.com/oauth/token"
        payload = {'grant_type': 'client_credentials','redirect_uri': 'https://localhost','scope': 'monitoring'}
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(token_url, data=payload, auth=(self.ninja_client_id, self.ninja_client_secret))
                response.raise_for_status()
                data = response.json()
                return data.get("access_token", None)
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to retrieve Ninja access token: {e.response.text}")
            return None  # Handle gracefully in fetch_ninja_data()
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return None

    async def fetch_ninja_data (self):
        access_token = await self.get_ninja_access_token()
        if not access_token:
            logger.error("Failed to fetch Ninja API token")
            return []
        headers = {"Authorization": f"Bearer {access_token}"}
        self.ninja_org_report = []
        # Fetch Ninja Organizations
        try:
            ninja_api_orgs_url = f"{NINJA_API_BASE_URL}/organizations"
            async with httpx.AsyncClient() as client:
                ninja_orgs_response = await client.get(ninja_api_orgs_url, headers=headers)
            ninja_orgs_response.raise_for_status()  # Ensure HTTP errors are handled
            ninja_orgs = ninja_orgs_response.json()# Parse the response

            # Process each organization
            for ninja_org in ninja_orgs:
                ninja_org_id = ninja_org.get("id")
                ninja_org_name = ninja_org.get("name")
                print(f"Processing Ninja Organization: {ninja_org_name}")
                if not ninja_org_id:
                    continue  # Skip if ID is missing

                try:
                    ninja_api_devices_url = f"{NINJA_API_BASE_URL}/organization/{ninja_org_id}/devices"
                    async with httpx.AsyncClient() as client:
                        ninja_devices_response = await client.get(ninja_api_devices_url, headers=headers)
                    ninja_devices_response.raise_for_status()

                    ninja_device_counts = {
                        "Number of Servers": 0,
                        "Number of Workstations": 0,
                        "Number of Clouds": 0,
                        "Number of VM Hosts": 0,
                        "Number of VM Guests": 0,
                    }

                    ninja_devices = ninja_devices_response.json()
                    for ninja_device in ninja_devices:
                        node_class = ninja_device.get("nodeClass")
                        if node_class in ["WINDOWS_SERVER", "MAC_SERVER", "LINUX_SERVER"]:
                            ninja_device_counts["Number of Servers"] += 1
                        elif node_class in ["WINDOWS_WORKSTATION", "MAC", "LINUX_WORKSTATION"]:
                            ninja_device_counts["Number of Workstations"] += 1
                        elif node_class == "CLOUD_MONITOR_TARGET":
                            ninja_device_counts["Number of Clouds"] += 1
                        elif node_class in ["VMWARE_VM_HOST", "HYPERV_VMM_HOST"]:
                            ninja_device_counts["Number of VM Hosts"] += 1
                        elif node_class in ["VMWARE_VM_GUEST", "HYPERV_VMM_GUEST"]:
                            ninja_device_counts["Number of VM Guests"] += 1

                    self.ninja_org_report.append({
                        "company_name": ninja_org_name,
                        "company_id": ninja_org_id,
                        **ninja_device_counts,
                    })

                except Exception as e:
                    raise ValueError(f"Error fetching devices for organization {ninja_org_id}: {e}")

        except Exception as e:
            raise ValueError(f"Error fetching Ninja data: {e}")
        
        return self.ninja_org_report
    
    async def make_bd_request(self, method, params):    
        try:
            headers = {"Content-Type": "application/json","Authorization": "Basic " + base64.b64encode(f"{self.bd_api_key}:".encode()).decode()}
            payload = {"jsonrpc": "2.0","method": method, "params": params,"id": self.bd_id}
            
            async with httpx.AsyncClient() as client:
                response = await client.post(BITDEFENDER_API_URL, json=payload, headers=headers)
                response.raise_for_status()
                return response.json()

        except httpx.HTTPError as e:
            logger.error(f"Error making Bitdefender API request: {e}")
            return {"error": {"message": "Request failed"}}  # Return a safe error structure
        
    async def fetch_bitdefender_data (self):
        self.bd_org_report = []  # Ensure this is initialized
        bd_org_params = {"filters": {"companyType": 1, "licenseType": 3}}

        bd_org_list = await self.make_bd_request("getCompaniesList", bd_org_params)
        if not isinstance(bd_org_list["result"], list):
            raise ValueError(f"Unexpected response format: {bd_org_list}")

        for bitdefender_org in bd_org_list["result"]:
            bd_org_id = bitdefender_org.get("id")
            bd_org_name = bitdefender_org.get("name")
            print(f"Processing Bitdefender Organization: {bd_org_name}")

            try:
                managed_bd_device_params = {"parentId": bd_org_id, "isManaged": True, "perPage": 100}
                bd_endpoints = await self.make_bd_request("getEndpointsList", managed_bd_device_params)
                if not isinstance(bd_endpoints["result"].get("items"), list):
                    continue
                
                endpoint_ids = [item["id"] for item in bd_endpoints["result"]["items"]]
                bd_licensed = sum(1 for e in bd_endpoints["result"]["items"] if e.get("licensed") == 1)
                bd_unlicensed = sum(1 for e in bd_endpoints["result"]["items"] if e.get("licensed") == 2)

                self.bd_org_report.append({
                    "Company_Name": bd_org_name,
                    "Managed": len(endpoint_ids),
                    "Licensed": bd_licensed,
                    "Expired_License": bd_unlicensed
                })
            
            except Exception as e:
                logger.error(f"Error processing Bitdefender organization {bd_org_name}: {e}")

        return self.bd_org_report
    
    async def generate_full_report(self):
        ninja_report, bd_report = await asyncio.gather(self.fetch_ninja_data(), self.fetch_bitdefender_data())
        app.state.ninja_report = ninja_report
        app.state.bd_report = bd_report

    # Render the HTML content using Jinja2 template
        report_data = {
            "ninja_report": ninja_report,
            "bd_report": bd_report
        }
        rendered_html = templates.get_template("report_template.html").render(report_data)

    # Generate a timestamped filename
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"MonthlyCounts_{timestamp}.html"
        filepath = os.path.join(reports_dir, filename)

    # Save the HTML content to the file
        with open(filepath, "w") as html_file:
            html_file.write(rendered_html)
            print(f"Report successfully saved to {filepath}!")

        return filepath  # Return the full path of the saved report

    async def run_script(self):

        self.generate_full_report()

        total_steps = 180  # Arbitrary number of steps to simulate
        for step in range(total_steps):
            self.progress = int((step + 1) / total_steps * 100)
            await asyncio.sleep(1)  # Simulate processing delay

# Instantiate the report generator
report_generator = ReportGenerator(
    ninja_client_id=ninja_client_id,
    ninja_client_secret=ninja_client_secret,
    bd_api_key=bd_api_key,
    bd_id=bd_id
)

# Routes and Endpoints
@app.get("/", response_class=HTMLResponse) # Route for the main page
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/generate_report/")
async def generate_report(background_tasks: BackgroundTasks):
    background_tasks.add_task(report_generator.run_script)
    return {"message": "Report generation started."}

@app.get("/progress/")
async def get_progress():
    return JSONResponse(content={"percent": report_generator.progress})

@app.get("/view_report/", response_class=HTMLResponse)
async def view_report(request: Request):
    # Retrieve the latest report file
    report_files = sorted(
        glob.glob(os.path.join(reports_dir, "MonthlyCounts_*.html")),
        key=os.path.getmtime,
        reverse=True
    )
    if not report_files:
        raise HTTPException(status_code=404, detail="No reports found.")
    
    latest_report_path = report_files[0]
    with open(latest_report_path, "r") as file:
        html_content = file.read()
    
    return HTMLResponse(content=html_content)

from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import StreamingResponse
import time
import json
import requests
import datetime
import base64
import os

# FastAPI app and templates setup
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

class ReportGenerator:
    def __init__(self, ninja_client_id, ninja_client_secret, bd_api_url, bd_api_key, bd_id):
        # Ensure credentials are valid
        if not all([ninja_client_id, ninja_client_secret, bd_api_url, bd_api_key, bd_id]):
            raise ValueError("All API credentials must be provided.")

        # Credentials
        self.ninja_client_id = ninja_client_id
        self.ninja_client_secret = ninja_client_secret
        self.bd_api_url = "https://cloud.gravityzone.bitdefender.com/api/v1.0/jsonrpc/network"
        self.bd_api_key = bd_api_key
        self.bd_id = bd_id

        # Data variables
        self.ninja_org_report = []  # Stores Ninja organization reports
        self.bd_org_report = []     # Stores Bitdefender organization reports
        self.progress_data = {"Stage": "", "Percent": 0}

        # Report placeholders
        self.ninja_html_report = ""
        self.bd_html_report = ""

    def get_ninja_access_token(self):
        token_url = "https://app.ninjarmm.com/oauth/token"
        payload = {'grant_type': 'client_credentials','redirect_uri': 'https://localhost','scope': 'monitoring'}
        response = requests.post(token_url, data=payload, verify=True, allow_redirects=False, auth=(self.ninja_client_id, self.ninja_client_secret))
        response.raise_for_status()
        return response.json().get("access_token")

    def fetch_ninja_data (self):
        access_token = self.get_ninja_access_token()
        headers = {"Authorization": f"Bearer {access_token}"}
        # Fetch Ninja Organizations
        try:
            ninja_api_orgs_url = "https://app.ninjarmm.com/api/v2/organizations"
            ninja_orgs_response = requests.get(ninja_api_orgs_url, headers=headers, verify=True)
            ninja_orgs_response.raise_for_status()  # Ensure HTTP errors are handled
            ninja_orgs = ninja_orgs_response.json()# Parse the response

            # Process each organization
            for ninja_org in ninja_orgs:
                ninja_org_id = ninja_org.get("id")
                ninja_org_name = ninja_org.get("name")
                self.progress_data["Stage"] = f"Processing Ninja Organization: {ninja_org_name}"
                if not ninja_org_id:
                    continue  # Skip if ID is missing

                try:
                    ninja_api_devices_url = f"https://app.ninjarmm.com/api/v2/organization/{ninja_org_id}/devices"
                    ninja_devices_response = requests.get(ninja_api_devices_url, headers=headers, verify=True)
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
    
    def make_bd_request(self, session, bd_api_url, method, params):        
        try:
            headers = {"Content-Type": "application/json","Authorization": "Basic " + base64.b64encode(f"{self.bd_api_key}:".encode()).decode()}
            payload = {"jsonrpc": "2.0","method": method, "params": params,"id": self.bd_id}
            response = session.post(bd_api_url, json=payload, verify=True, headers=headers)
            response.raise_for_status()  # Ensure we catch HTTP errors
            return response.json()  # Directly return JSON response
        except requests.RequestException as e:
            print(f"Error making Bitdefender API request: {e}")
            return {"error": {"message": "Request failed"}}  # Return a safe error structure
        
    def fetch_bitdefender_data (self):
        session = requests.Session()
        self.bd_org_report = []  # Ensure this is initialized

        try:
            bd_org_params = {"filters": {"companyType": 1, "licenseType": 3}}
            bd_org_list = self.make_bd_request(session, self.bd_api_url, "getCompaniesList", bd_org_params)
            if "result" not in bd_org_list or not isinstance(bd_org_list["result"], list):
                raise ValueError(f"Unexpected response format: {bd_org_list}")
            
            for bd_org in bd_org_list["result"]:
                bd_org_id = bd_org.get("id")
                bd_org_name = bd_org.get("name")
                self.progress_data["Stage"] = f"Processing Bitdefender Organization: {bd_org_name}"

                try:
                    # For each company, fetch all the endpoint IDs
                    managed_bd_device_params = {"parentId": bd_org_id, "isManaged": True, "perPage": 100}
                    bd_endpoints = self.make_bd_request(session, self.bd_api_url, "getEndpointsList", managed_bd_device_params)
                    if "result" in bd_endpoints and isinstance(bd_endpoints["result"].get("items"), list):
                        endpoint_ids = [item["id"] for item in bd_endpoints["result"]["items"]]
                        bd_licensed = 0
                        bd_unlicensed = 0

                        # For each endpoint, fetch license status
                        for endpoint_id in endpoint_ids:
                            bd_endpoint_detail_params = {"endpointId": endpoint_id}
                            bd_endpoint_details = self.make_bd_request(session, self.bd_api_url, "getManagedEndpointDetails", bd_endpoint_detail_params)
                            
                            if "result" in bd_endpoint_details and "agent" in bd_endpoint_details["result"]:
                                licensed = bd_endpoint_details["result"]["agent"].get("licensed", 0)
                                if licensed == 1:
                                    bd_licensed += 1
                                elif licensed == 2:
                                    bd_unlicensed += 1

                        self.bd_org_report.append({
                            "Company_Name": bd_org_name,
                            "Managed": len(endpoint_ids),
                            "Licensed": bd_licensed,
                            "Expired_License": bd_unlicensed
                        })
                
                except Exception as e:
                    print(f"Error fetching endpoint/license data for company {bd_org_name}: {e}")

        except Exception as e:
            print(f"Unexpected Bitdefender API response format: {bd_org_list}")
            return []  # Return an empty list instead of None to avoid iteration errors

        return self.bd_org_report
    
    def create_ninja_html_report(self):
        self.progress_data["Stage"] = "Generating Ninja HTML Report..."
        # Initialize HTML report
        self.ninja_html_report = """   
            <h1>Ninja RMM Equipment Report</h1>
            <table>
                <tr class="sticky-top">
                    <th>Company Name</th>
                    <th>Number of Servers</th>
                    <th>Number of Workstations</th>
                    <th>Number of Clouds</th>
                    <th>Number of VM Hosts</th>
                    <th>Number of VM Guests</th>
                </tr>
        """
        for report in self.ninja_org_report:
            self.ninja_html_report += f"""
                <tr>
                    <td>{report['company_name']}</td>
                    <td>{report['Number of Servers']}</td>
                    <td>{report['Number of Workstations']}</td>
                    <td>{report['Number of Clouds']}</td>
                    <td>{report['Number of VM Hosts']}</td>
                    <td>{report['Number of VM Guests']}</td>
                </tr>
            """
        self.ninja_html_report += """
            </table>
        """
        return self.ninja_html_report

    def create_bd_html_report(self):
        self.progress_data["Stage"] = "Generating Bitdefender HTML Report..."
        # Initialize HTML report
        self.bd_html_report = """
            <h1>Bitdefender Equipment Report</h1>
            <table>
                <tr class="sticky-top">
                    <th>Company Name</th>
                    <th>Managed Equipment Count</th>
                    <th>Active License Count</th>
                    <th>Expired License Count</th>
                </tr>
        """
        for report in self.bd_org_report:
            self.bd_html_report += f"""
                <tr>
                    <td>{report['Company_Name']}</td>
                    <td>{report['Managed']}</td>
                    <td>{report['Licensed']}</td>
                    <td>{report['Expired_License']}</td>
                </tr>
            """
        self.bd_html_report += """
            </table>
        """
        return self.bd_html_report

    def generate_full_report(self):
        html_head = """
        <!DOCTYPE html>
        <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Monthly Device Counts Report Generator</title>
                <link rel="stylesheet" type="text/css" href="/static/css/styles.css">
                <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" integrity="sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH" crossorigin="anonymous">
        </head>
        <body>
            <section class="container d-flex flex-column align-items-center">
        """
        html_content = html_head + self.ninja_html_report + self.bd_html_report + "</section></body></html>"

        # Define the "reports" directory within the project's directory
        project_dir = os.path.dirname(os.path.abspath(__file__))
        reports_dir = os.path.join(project_dir, "reports")

        # Create the "reports" directory if it doesn't exist
        os.makedirs(reports_dir, exist_ok=True)

        # Generate a timestamp for the filename
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"MonthlyCounts_{timestamp}.html"
        filepath = os.path.join(reports_dir, filename)

        # Save the HTML content to the file
        with open(filepath, "w") as html_file:
            html_file.write(html_content)
            print(f"Report successfully saved to {filepath}!")
        return filepath  # Return the full path of the saved report
    
    def get_most_recent_report(self):
        reports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
        # Check if the directory exists and contains files
        if not os.path.exists(reports_dir) or not os.listdir(reports_dir):
            return None

        # Find the most recent file in the "reports" directory
        reports = [os.path.join(reports_dir, f) for f in os.listdir(reports_dir) if f.endswith(".html")]
        if not reports:
            return None

        latest_report = max(reports, key=os.path.getctime)  # Sort by creation time
        return latest_report

    def run_script(self, background_tasks: BackgroundTasks):
        self.progress_data = {"Stage": "Starting process...", "Percent": 0}

        try:
            # Fetch Ninja data
            self.fetch_ninja_data()
            self.create_ninja_html_report()
            self.progress_data["Percent"] = 50  # Halfway done

            # Fetch Bitdefender data
            self.fetch_bitdefender_data()
            self.create_bd_html_report()
            self.progress_data["Percent"] = 90  # Almost done

            # Generate report
            self.progress_data["Stage"] = "Generating full report"
            self.progress_data["Percent"] = 99
            return self.generate_full_report()

        except Exception as e:
            self.progress_data = {"Stage": "Error", "Company": "N/A", "Percent": 100}
            print(f"Error during report generation: {e}")
            raise

def generate_progress():
    for message in ReportGenerator.progress_data:
        yield f"data: {message}\n\n"
        time.sleep(1) # Simulate a delay for updates

# Instantiate the report generator
report_generator = ReportGenerator(
    ninja_client_id="placeholder_string",
    ninja_client_secret="placeholder_string",
    bd_api_key="placeholder_string",
    bd_id="placeholder_string"
)

# Routes and Endpoints
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/generate_report/")
async def generate_report(background_tasks: BackgroundTasks):
    background_tasks.add_task(report_generator.run_script, background_tasks)
    return {"message": "Report generation started"}

@app.get("/progress/")
async def progress_stream():
    return StreamingResponse(generate_progress(), media_type="text/event-stream")

@app.get("/view-report/", response_class=HTMLResponse)
async def view_report():
    latest_report = report_generator.get_most_recent_report()
    if not latest_report:
        return HTMLResponse("<h1>No reports found!</h1>", status_code=404)
    with open(latest_report, "r", encoding="utf-8") as file:
        report_content = file.read()
    return HTMLResponse(content=report_content)

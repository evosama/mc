document.getElementById("generateButton").addEventListener("click", () => {
    generateReport();
  });
  
// Function to start the report generation process
async function generateReport() {
    let response = await fetch("/generate_report/", { method: "POST" });
    let data = await response.json();
    console.log(data.message);
    //let progressBar = document.getElementById("progressBar");
    let progressContainer = document.getElementById("progressContainer");
    let generateButton = document.getElementById("generateButton");
    let reportFrame = document.getElementById("reportFrame");

    // Reset UI: Clear iframe, reset progress bar and text
    progressContainer.style.display = "block";
    generateButton.disabled = true;
    reportFrame.style.display = "none";
    reportFrame.src = ""; // Clear the iframe content

    // Trigger the backend to start polling progress
    async function updateProgress() {
        const response = await fetch("/progress/");
        const data = await response.json();
    
        if (data.percent !== undefined) {
            const progressBar = document.getElementById("progressBar");
            progressBar.style.width = `${data.percent}%`;
            progressBar.innerText = `${data.percent}%`;
    
            if (data.percent >= 100) {
                clearInterval(progressInterval);
                const reportFrame = document.getElementById("reportFrame");
                reportFrame.src = "/view_report/"; 
                reportFrame.style.display = "block";
            }
        }
    }
    let progressInterval = setInterval(updateProgress, 2000); // Poll progress every 2 seconds
}

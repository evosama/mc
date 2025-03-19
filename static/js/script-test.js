document.getElementById("generateButton").addEventListener("click", () => {
    generateReport();
  });
  
// Function to start the report generation process
async function generateReport() {
    let response = await fetch("/generate_report/", { method: "POST" });
    let data = await response.json();
    console.log(data.message);
    let progressBar = document.getElementById("progressBar");
    let progressContainer = document.getElementById("progressContainer");
    let generateButton = document.getElementById("generateButton");
    let reportFrame = document.getElementById("reportFrame");

    // Reset UI: Clear iframe, reset progress bar and text
    progressContainer.style.display = "block";
    generateButton.disabled = true;
    reportFrame.style.display = "none";
    reportFrame.src = ""; // Clear the iframe content

    // Trigger the backend to start report generation
    function updateProgress() {
    fetch("/progress/")
        .then(response => response.json())
        .then(progress => {
            progressBar.style.width = progress.Percent + "%";
            progressBar.innerText = progress.Stage + " - " + progress.Company + " (" + progress.Percent + "%)";
            if (progress.Percent >= 100) {
                clearInterval(progressInterval); // Stop checking progress
                reportFrame.src = "/view-report/"; // Load the completed report
            } else {
                progressContainer.style.display = "none";
                generateButton.innerText = "Restart Progress";
                generateButton.disabled = false;
                reportFrame.src = "/view-report/";
                reportFrame.style.display = "block";
            }
        })
        .catch(error => console.error("Error fetching progress:", error));
    }
    let progressInterval = setInterval(updateProgress, 2000); // Poll progress every 2 seconds
}

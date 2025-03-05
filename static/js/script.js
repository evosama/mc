document.getElementById("generateButton").addEventListener("click", () => {
    generateReport();
  });
  
// Function to start the report generation process
function generateReport() {
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
    fetch("/generate_report/", { method: "POST" })
        .then(response => response.json())
        .then(data => {
            let totalItems = data.total;
            function updateProgress() {
            fetch("/progress/")
                .then((response) => response.json())
                .then(progressData => {
                    let completed = progressData.completed;
                    let progress = (completed / totalItems) * 100;
                    progressBar.style.width = progress + "%";
                    progressBar.innerText = Math.round(progress) + "%";
                    if (completed < totalItems) {
                        setTimeout(updateProgress, 500);
                    } else {
                        progressContainer.style.display = "none";
                        generateButton.innerText = "Restart Progress";
                        generateButton.disabled = false;
                        reportFrame.src = "/view-report/";
                        reportFrame.style.display = "block";
                    }
                })
            }
            updateProgress();
        });
}

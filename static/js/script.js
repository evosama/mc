document.getElementById("generateButton").addEventListener("click", () => {
    generateReport();
  });
  
// Function to start the report generation process
async function generateReport() {
    await fetch("/generate_report/", { method: "POST" });

    const progressInterval = setInterval(async () => {
        const response = await fetch("/progress/");
        const data = await response.json();

        const progressBar = document.getElementById("progressBar");
        progressBar.style.width = `${data.percent}%`;
        progressBar.innerText = `${data.percent}%`;

        if (data.percent >= 100) {
            clearInterval(progressInterval);
            const reportFrame = document.getElementById("reportFrame");
            reportFrame.src = "/view_report/";
            reportFrame.style.display = "block";
        }
    }, 1000); // Update every second
}

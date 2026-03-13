// 1. Initialize Viewer (Optimized)
const viewer = new Cesium.Viewer("cesiumContainer", {
    baseLayer: new Cesium.ImageryLayer(
        new Cesium.OpenStreetMapImageryProvider({
            url: "https://a.tile.openstreetmap.org/"
        })
    ),
    geocoder: false,
    homeButton: false,
    sceneModePicker: false,
    navigationHelpButton: false,
    animation: false,
    timeline: false
});

// 2. Load Year Function
window.loadHistoryYear = async function (year) {
    try {
        // Fetch the specific file from your /data folder
        const response = await fetch(`./data/${year}.json`);

        if (!response.ok) {
            alert(`No data found for the year ${year}`);
            return;
        }

        const events = await response.json();

        // Clear previous markers
        viewer.entities.removeAll();

        // Add new markers
        events.forEach(event => {
            viewer.entities.add({
                name: event.title,
                position: Cesium.Cartesian3.fromDegrees(event.lon, event.lat),
                point: {
                    pixelSize: 10,
                    color: Cesium.Color.RED,
                    outlineColor: Cesium.Color.WHITE,
                    outlineWidth: 2
                },
                description: `
                    <div style="padding:10px;">
                        <strong>Date:</strong> ${event.date}<br/><br/>
                        ${event.description}<br/><br/>
                        <a href="${event.wikiLink}" target="_blank" style="color:#448aff">Wikipedia Article</a>
                    </div>
                `
            });
        });

        // Optional: Fly to the first event in the list
        if (events.length > 0) {
            viewer.camera.flyTo({
                destination: Cesium.Cartesian3.fromDegrees(events[0].lon, events[0].lat, 1000000)
            });
        }

    } catch (error) {
        console.error("Error loading history data:", error);
    }
};

// Uncomment to debug Cesium Inspector (lat/lon lines)
// viewer.extend(Cesium.viewerCesiumInspectorMixin);

# Beaver Dam Environmental Impact Analysis Tool

A Streamlit-based web application for analyzing the environmental impacts of beaver dams using satellite imagery and geospatial analysis.

## Quick Start

### Prerequisites
- Python 3.8 or higher
- Google Earth Engine account with service credentials
- Git

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd beaver-app-st
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up Google Earth Engine credentials:**
   - Create a service account in Google Cloud Console
   - Download the service account key JSON file
   - Configure Streamlit secrets (see Configuration section below)

4. **Run the application:**
   ```bash
   streamlit run app.py
   ```

5. **Access the tool:**
   - Open your browser to `http://localhost:8501`
   - Follow the 6-step workflow in the main interface

## Configuration

### Google Earth Engine Setup

Create a `.streamlit/secrets.toml` file in your project root:

```toml
[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-private-key-id"
private_key = "-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY_HERE\n-----END PRIVATE KEY-----\n"
client_email = "your-service-account@your-project.iam.gserviceaccount.com"
client_id = "your-client-id"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/your-service-account%40your-project.iam.gserviceaccount.com"
```

**Important:** Never commit the secrets.toml file to version control.

## Using the Tool

### 6-Step Analysis Workflow

1. **Upload Dam Locations**
   - Upload CSV or GeoJSON files containing dam coordinates
   - Required fields: latitude, longitude, date (YYYY-MM-DD format)

2. **Select Waterway Data**
   - Choose relevant waterway datasets for your study area
   - Tool automatically filters by geographic bounds

3. **Validate Dam Locations**
   - Review dam locations for accuracy
   - Check proximity to waterways
   - Remove invalid points if necessary

4. **Generate Non-Dam Locations**
   - Upload existing non-dam points OR
   - Auto-generate negative samples using spatial algorithms

5. **Create Analysis Buffers**
   - Set buffer radius (default: 150 meters)
   - Apply elevation masking (±3 meters from dam elevation)

6. **Analyze Environmental Metrics**
   - Calculate NDVI (vegetation index)
   - Calculate NDWI (water index)
   - Calculate LST (land surface temperature)
   - Calculate ET (evapotranspiration)
   - Generate time series visualizations

### Input Data Requirements

**Dam Location Files:**
- Format: CSV or GeoJSON
- Required columns: `latitude`, `longitude`, `date`
- Date format: YYYY-MM-DD
- Coordinate system: WGS84 (EPSG:4326)

**Example CSV format:**
```csv
latitude,longitude,date
45.123,-122.456,2020-07-15
45.234,-122.567,2020-08-20
```

## Output Data

The tool generates:
- **Time series plots:** Monthly environmental metrics over time
- **Comparison analysis:** Dam vs non-dam areas
- **Upstream/downstream analysis:** Flow direction impacts
- **Exportable data:** CSV files with calculated metrics
- **Interactive maps:** Visualizations of analysis areas

## Metrics Calculated

- **NDVI:** Normalized Difference Vegetation Index - measures vegetation health
- **NDWI:** Normalized Difference Water Index - measures water content
- **LST:** Land Surface Temperature - measures thermal conditions
- **ET:** Evapotranspiration - measures water-energy exchange

## Troubleshooting

### Common Issues

**"Memory limit exceeded" errors:**
- Reduce batch size in processing
- Use smaller study areas
- Process data in smaller time windows

**"No images found" errors:**
- Check date ranges in input data
- Verify geographic coordinates are valid
- Ensure study area has satellite coverage

**Authentication errors:**
- Verify Google Earth Engine credentials
- Check service account permissions
- Ensure project is enabled for Earth Engine

---

## Developer Documentation

### Architecture Overview

The Beaver Impacts Tool is built on:
- **Streamlit**: For the web interface
- **Google Earth Engine (GEE)**: For satellite imagery processing
- **Pandas/NumPy**: For data manipulation
- **Seaborn/Matplotlib**: For visualization

The application follows a step-by-step workflow where users:
1. Upload dam locations
2. Select waterway datasets
3. Validate dam locations
4. Generate or upload non-dam locations
5. Create buffered analysis zones
6. Analyze and visualize environmental metrics

Each step involves interactions between the frontend (Streamlit) and backend processing using Earth Engine's Python API.

### Code Structure

```
beaver-app-st/
├── app.py                      # Main Streamlit application entry point
├── pages/                      # Streamlit pages
│   ├── About_Lab.py           # About page
│   ├── Exports_page.py        # Main analysis workflow (primary functionality)
│   └── Quick_analysis.py      # Quick analysis features
├── service/                    # Core business logic modules
│   ├── Data_management.py     # Data management utilities
│   ├── Export_dam_imagery.py  # Image export functionality
│   ├── Negative_sample_functions.py # Non-dam point generation
│   ├── Parser.py              # Data parsing and input handling
│   ├── Sentinel2_functions.py # Sentinel-2 image processing
│   ├── Validation_service.py  # Data validation logic
│   ├── Visualize_trends.py    # Visualization and metrics computation
│   ├── earth_engine_auth.py   # Earth Engine authentication
│   ├── constants.py           # Centralized constants
│   ├── batch_processing.py    # Batch processing utilities
│   └── common_utilities.py    # Common utility functions
├── assets/                     # Static assets and images
└── requirements.txt           # Python dependencies
```

### Key Implementation Patterns

#### Earth Engine Authentication
The application uses Google Earth Engine service account credentials stored in Streamlit secrets:
```python
credentials_info = {
    "type": st.secrets["gcp_service_account"]["type"],
    "project_id": st.secrets["gcp_service_account"]["project_id"],
    # Other credentials from secrets
}
ee.Initialize(credentials, project="ee-beaver-lab")
```

#### Session State Management
Uses Streamlit's session state extensively to maintain application state across user interactions:
```python
if "Positive_collection" not in st.session_state:
    st.session_state.Positive_collection = None
```

#### Batch Processing Pattern
Critical pattern for managing Earth Engine memory limits:
```python
total_count = Dam_data.size().getInfo()
batch_size = 10  # Adjust based on data complexity
num_batches = (total_count + batch_size - 1) // batch_size

for i in range(num_batches):
    dam_batch = Dam_data.toList(batch_size, i * batch_size)
    dam_batch_fc = ee.FeatureCollection(dam_batch)
    # Process batch...
```

### Data Processing Pipeline

The application implements a 6-step workflow:

1. **Point Data Upload**: CSV/GeoJSON files with dam locations
2. **Standardization**: Assigns unique IDs (P1, P2... for dams; N1, N2... for non-dams)
3. **Buffer Creation**: Creates 150m radius buffers with elevation masking (±3m)
4. **Satellite Image Acquisition**: Filters Sentinel-2 imagery with cloud masking
5. **Metric Computation**: Calculates NDVI, NDWI, LST (Land Surface Temperature), and ET (Evapotranspiration)
6. **Visualization**: Time series plots comparing dam vs non-dam areas

### Earth Engine Integration

#### Cloud Masking
```python
def cloud_mask(image):
    qa = image.select('QA_PIXEL')
    mask = qa.bitwiseAnd(1 << 3).eq(0).And(
           qa.bitwiseAnd(1 << 5).eq(0))
    return image.updateMask(mask)
```

#### LST Calculation
Complex Land Surface Temperature calculation using NDVI-based emissivity:
```python
def robust_compute_lst(filtered_col, boxArea):
    ndvi = img.normalizedDifference(['SR_B5', 'SR_B4']).rename('NDVI')
    fv = ndvi.subtract(ndvi_min).divide(ndvi_max.subtract(ndvi_min)).pow(2)
    em = fv.multiply(0.004).add(0.986).rename('EM')
    lst = thermal.expression(
        '(TB / (1 + (0.00115 * (TB / 1.438)) * log(em))) - 273.15',
        {'TB': thermal, 'em': em}
    )
    return lst
```

### Development Notes

- **Memory Management**: Always use batch processing for large datasets to avoid Earth Engine memory limits
- **Error Handling**: Implement try-catch blocks around Earth Engine operations
- **Data Validation**: Validate coordinate formats and date ranges before processing
- **Cloud Coverage**: Use cloud masking and select least cloudy images (< 20% cloud coverage)
- **Authentication**: Ensure Earth Engine credentials are properly configured in Streamlit secrets

### Adding New Features

To add new features to the application:

1. **Add new Earth Engine functions**:
   - Create functions in the appropriate service module
   - Ensure proper error handling
   - Test processing on small datasets first

2. **Add new UI components**:
   - Add new sections to the appropriate Streamlit page
   - Use `st.session_state` to maintain state
   - Follow the step pattern of existing code

3. **Add new metrics**:
   - Modify the `compute_all_metrics_LST_ET` function
   - Add processing code for the new metric
   - Update visualization code to include the new metric

### Dependencies

This is a Python application using Earth Engine Python API. Main dependencies include:
- `streamlit`: Web framework
- `earthengine-api`: Google Earth Engine Python API
- `geemap`: Earth Engine integration tools
- `pandas`, `numpy`: Data manipulation
- `matplotlib`, `seaborn`: Visualization
- `folium`: Interactive maps
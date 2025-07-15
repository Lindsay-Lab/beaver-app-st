# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

**Start the Streamlit application:**
```bash
streamlit run app.py
```

**Install dependencies:**
```bash
pip install -r requirements.txt
```

## Architecture Overview

This is a Streamlit-based geospatial analysis tool for analyzing beaver dam impacts using satellite imagery. The application integrates with Google Earth Engine for satellite image processing and analysis.

**Key Technologies:**
- **Streamlit**: Web interface and multi-page application framework
- **Google Earth Engine**: Satellite imagery processing and geospatial analysis
- **Pandas/NumPy**: Data manipulation and analysis
- **Matplotlib/Seaborn**: Data visualization and plotting

## Code Structure

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
│   └── Visualize_trends.py    # Visualization and metrics computation
├── assets/                     # Static assets and images
└── requirements.txt           # Python dependencies
```

## Key Implementation Patterns

### Earth Engine Authentication
The application uses Google Earth Engine service account credentials stored in Streamlit secrets:
```python
credentials_info = {
    "type": st.secrets["gcp_service_account"]["type"],
    "project_id": st.secrets["gcp_service_account"]["project_id"],
    # Other credentials from secrets
}
ee.Initialize(credentials, project="ee-beaver-lab")
```

### Session State Management
Uses Streamlit's session state extensively to maintain application state across user interactions:
```python
if "Positive_collection" not in st.session_state:
    st.session_state.Positive_collection = None
```

### Batch Processing Pattern
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

## Data Processing Pipeline

The application implements a 6-step workflow:

1. **Point Data Upload**: CSV/GeoJSON files with dam locations
2. **Standardization**: Assigns unique IDs (P1, P2... for dams; N1, N2... for non-dams)
3. **Buffer Creation**: Creates 150m radius buffers with elevation masking (±3m)
4. **Satellite Image Acquisition**: Filters Sentinel-2 imagery with cloud masking
5. **Metric Computation**: Calculates NDVI, NDWI, LST (Land Surface Temperature), and ET (Evapotranspiration)
6. **Visualization**: Time series plots comparing dam vs non-dam areas

## Earth Engine Integration

### Cloud Masking
```python
def cloud_mask(image):
    qa = image.select('QA_PIXEL')
    mask = qa.bitwiseAnd(1 << 3).eq(0).And(
           qa.bitwiseAnd(1 << 5).eq(0))
    return image.updateMask(mask)
```

### LST Calculation
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

## Development Notes

- **Memory Management**: Always use batch processing for large datasets to avoid Earth Engine memory limits
- **Error Handling**: Implement try-catch blocks around Earth Engine operations
- **Data Validation**: Validate coordinate formats and date ranges before processing
- **Cloud Coverage**: Use cloud masking and select least cloudy images (< 20% cloud coverage)
- **Authentication**: Ensure Earth Engine credentials are properly configured in Streamlit secrets

## Code Quality & Development Workflow

### Automated Code Formatting
This repository uses automated code formatting tools to maintain consistent code style:

**Tools configured:**
- **autoflake**: Automatically removes unused imports
- **isort**: Sorts and organizes imports (Black-compatible)
- **black**: Code formatter with 125-character line length
- **flake8**: Linter with custom rules (E501 ignored for line length)

**Pre-commit hooks:**
```bash
# Install pre-commit hooks
pre-commit install

# Run manually on all files
pre-commit run --all-files
```

**Manual formatting:**
```bash
# Full formatting pipeline
autoflake --remove-all-unused-imports --recursive --in-place .
isort .
black .
flake8 .
```

### Journal Publication Roadmap

**Phase 1: Code Formatting & Linting (✅ COMPLETED)**
- ✅ Implement Black, isort, autoflake formatting
- ✅ Remove unused imports automatically
- ✅ Set up pre-commit hooks
- ✅ Configure 125-character line length
- ✅ Exclude virtual environment from tools

**Phase 2: Code Organization & Structure (NEXT)**
- Remove large commented code blocks
- Break down monolithic functions (>200 lines)
- Separate UI logic from business logic
- Create configuration management for constants
- Standardize error handling patterns

**Phase 3: Documentation & Testing (FUTURE)**
- Add comprehensive docstrings and type hints
- Implement unit tests for core functions
- Add integration tests for Earth Engine operations
- Create proper logging instead of st.write debugging
- Add input validation and sanitization

**Phase 4: Performance & Security (FUTURE)**
- Refactor duplicate Earth Engine initialization
- Implement caching for expensive operations
- Improve batch processing efficiency
- Enhance credentials handling security
- Add comprehensive input validation

### Development Standards
- **Line Length**: 125 characters (configured in pyproject.toml)
- **Import Style**: Black-compatible with isort
- **Error Handling**: Specific exceptions preferred over broad catches
- **Comments**: Use `# ` prefix for inline comments
- **Testing**: Required for new functionality
- **Documentation**: Docstrings required for all public functions

## Dependencies

This is a Python application using Earth Engine Python API. Main dependencies include:
- `streamlit`: Web framework
- `earthengine-api`: Google Earth Engine Python API
- `geemap`: Earth Engine integration tools
- `pandas`, `numpy`: Data manipulation
- `matplotlib`, `seaborn`: Visualization
- `folium`: Interactive maps

**Development dependencies:**
- `autoflake`: Unused import removal
- `black`: Code formatting
- `isort`: Import sorting
- `flake8`: Linting
- `pre-commit`: Git hooks
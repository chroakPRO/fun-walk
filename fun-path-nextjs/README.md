# Fun Path Planner

A TypeScript Next.js application that finds the most enjoyable walking routes between two points, inspired by the original Python implementation. Built with modern web technologies and a beautiful UI using shadcn/ui components.

## Features

- **Interactive Route Planning**: Enter start and destination coordinates to calculate multiple route options
- **Multiple Route Types**: 
  - **Shortest Route**: Fastest direct path
  - **Most Fun Route**: Maximizes scenic value and interesting paths
  - **Balanced Route**: Good mix of speed and enjoyment
- **Interactive Map**: Leaflet-based map with detailed route visualization
- **Detailed Analysis**: Comprehensive breakdown of path types, surfaces, and special areas
- **Modern UI**: Clean, responsive design with shadcn/ui components
- **Terminal Theme**: Retains the hacker aesthetic of the original Python version

## Technology Stack

- **Framework**: Next.js 15 with TypeScript
- **UI Components**: shadcn/ui with Tailwind CSS
- **Maps**: Leaflet with OpenStreetMap tiles
- **Icons**: Lucide React
- **Styling**: Tailwind CSS with custom terminal theme

## Getting Started

### Prerequisites

- Node.js 18+ 
- npm or yarn

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd fun-path-nextjs
```

2. Install dependencies:
```bash
npm install
```

3. Run the development server:
```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

4. Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

## Usage

1. **Enter Coordinates**: Input latitude and longitude for start and destination points
2. **Use Current Location**: Click the button to automatically use your current location as the start point
3. **Calculate Routes**: Click "Calculate Fun Routes" to generate multiple route options
4. **Explore Results**: 
   - View routes on the interactive map
   - Compare route statistics and details
   - Read detailed analysis and recommendations

## API Endpoints

### POST /api/routes

Calculate multiple route options between two points.

**Request Body:**
```typescript
{
  start: { lat: number, lng: number },
  end: { lat: number, lng: number },
  buffer_dist?: number
}
```

**Response:**
```typescript
{
  routes: Route[],
  success: boolean,
  error?: string
}
```

## Route Types

### Shortest Route
- Optimized for speed and directness
- Minimal detours
- Best for time-sensitive travel

### Most Fun Route  
- Maximizes scenic value and interesting paths
- Prioritizes parks, trails, and natural areas
- Higher fun score calculation

### Balanced Route
- Combines efficiency with enjoyment
- Good compromise between speed and scenery
- Weighted optimization of both factors

## Route Analysis

Each route includes detailed statistics:

- **Distance & Time**: Total distance and estimated walking time
- **Fun Score**: Calculated based on path types and special areas
- **Path Types**: Breakdown of sidewalks, trails, paths, etc.
- **Surface Analysis**: Paved, unpaved, grass, sand surfaces
- **Special Areas**: Parks, forests, viewpoints, attractions
- **Speed Analysis**: Average walking speed based on terrain

## OSM-Based Routing Engine

This application implements the same routing logic as the original Python script using OpenStreetMap data:

- **Overpass API**: Downloads walking network data (footways, paths, trails, parks)
- **Graph-Based Routing**: Builds a walkable network graph like OSMnx in Python
- **Fun Weight Algorithm**: Applies the same scoring system as the Python script
- **Multiple Route Types**: Shortest, Most Fun, and Balanced routes using Dijkstra's algorithm
- **Nominatim**: Geocoding service for address-to-coordinate conversion

### How It Works

1. **Network Download**: Queries Overpass API for walking paths in the area
2. **Graph Building**: Creates nodes and edges with distance and fun weight calculations
3. **Fun Scoring**: Applies weights based on path types (trails=+2.0, parks=+1.5, viewpoints=+3.0)
4. **Route Calculation**: Uses Dijkstra's algorithm with different weight strategies
5. **Multiple Options**: Generates shortest (distance), most fun (fun weight), and balanced routes

This matches the Python script's approach but runs entirely in the browser without needing a backend.

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.

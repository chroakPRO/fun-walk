#!/usr/bin/env node

// Simple test script to verify our OSM routing engine
// Tests with the exact coordinates from the Python script

const { OSMRoutingEngine } = require('./dist/services/osmRouting.js');

async function testRouting() {
  console.log('Testing OSM Routing Engine...');
  console.log('Using coordinates from Python script:');
  
  const start = { lat: 58.508594, lng: 15.487358 };
  const end = { lat: 58.490666, lng: 15.498153 };
  
  console.log(`Start: ${start.lat}, ${start.lng}`);
  console.log(`End: ${end.lat}, ${end.lng}`);
  console.log('');
  
  try {
    console.log('Fetching walking network...');
    const graph = await OSMRoutingEngine.fetchWalkingNetwork(start, end, 5000);
    
    console.log(`Graph built with ${graph.nodes.size} nodes and ${graph.ways.size} ways`);
    
    const startNode = OSMRoutingEngine.findNearestNode(graph, start);
    const endNode = OSMRoutingEngine.findNearestNode(graph, end);
    
    console.log(`Start node: ${startNode}, End node: ${endNode}`);
    
    if (startNode && endNode) {
      console.log('Finding shortest path...');
      const path = OSMRoutingEngine.findShortestPath(graph, startNode, endNode, true);
      
      if (path) {
        console.log(`SUCCESS: Found path with ${path.length} nodes`);
        
        // Calculate route stats
        const coordinates = path.map(nodeId => {
          const node = graph.nodes.get(nodeId);
          return { lat: node.lat, lng: node.lng };
        });
        
        let totalDistance = 0;
        for (let i = 0; i < coordinates.length - 1; i++) {
          const dist = calculateDistance(coordinates[i], coordinates[i + 1]);
          totalDistance += dist;
        }
        
        console.log(`Total distance: ${totalDistance.toFixed(0)}m (${(totalDistance/1000).toFixed(2)}km)`);
        console.log(`Estimated time: ${(totalDistance/1000 * 60/4.2).toFixed(0)} minutes`);
        
      } else {
        console.log('ERROR: No path found');
      }
    } else {
      console.log('ERROR: Could not find start or end nodes');
    }
    
  } catch (error) {
    console.error('Error:', error.message);
  }
}

function calculateDistance(coord1, coord2) {
  const R = 6371000; // Earth's radius in meters
  const dLat = (coord2.lat - coord1.lat) * Math.PI / 180;
  const dLng = (coord2.lng - coord1.lng) * Math.PI / 180;
  const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
            Math.cos(coord1.lat * Math.PI / 180) * Math.cos(coord2.lat * Math.PI / 180) *
            Math.sin(dLng/2) * Math.sin(dLng/2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
  return R * c;
}

testRouting().catch(console.error);
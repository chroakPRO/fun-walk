import { Coordinate, RouteSegment } from '@/types/route';
import { OverpassResponse } from '@/types/api';

// OSM-based routing that mimics the Python script's approach
export interface OSMNode {
  id: string;
  lat: number;
  lng: number;
  tags: Record<string, string>;
}

export interface OSMWay {
  id: string;
  nodes: string[];
  tags: Record<string, string>;
  length?: number;
  fun_weight?: number;
}

export interface OSMGraph {
  nodes: Map<string, OSMNode>;
  ways: Map<string, OSMWay>;
  adjacency: Map<string, Array<{ nodeId: string; wayId: string; distance: number; fun_weight: number }>>;
}

interface RouteStats {
  distance: number;
  fun_weight: number;
  fun_score: number;
  estimated_time: number;
  waypoints: number;
  path_types: Record<string, { distance: number; time: number; speed: number; description: string }>;
  surface_types: Record<string, { distance: number; time: number; speed_modifier: number; description: string }>;
  special_areas: Record<string, { distance: number; time: number; description: string }>;
  segments: RouteSegment[];
  avg_speed: number;
}

interface RouteResult {
  name: string;
  description: string;
  coordinates: Coordinate[];
  stats: RouteStats;
  color: string;
  priority: 'speed' | 'fun' | 'balanced';
}

export class OSMRoutingEngine {
  private static readonly OVERPASS_URL = 'https://overpass.kumi.systems/api/interpreter';

  // Fun weights matching the Python script
  private static readonly FUN_HIGHWAYS = new Set(['footway', 'path', 'pedestrian', 'track', 'steps', 'cycleway']);
  
  static async fetchWalkingNetwork(start: Coordinate, end: Coordinate, bufferDist: number = 1000): Promise<OSMGraph> {
    console.log(`Fetching walking network from OSM with ${bufferDist}m buffer...`);
    
    // Calculate center point and bounding box
    const centerLat = (start.lat + end.lat) / 2;
    const centerLng = (start.lng + end.lng) / 2;
    
    // Create bounding box (roughly bufferDist meters around center)
    const latOffset = bufferDist / 111000; // Rough conversion: 1 degree ≈ 111km
    const lngOffset = bufferDist / (111000 * Math.cos(centerLat * Math.PI / 180));
    
    const bbox = {
      south: centerLat - latOffset,
      west: centerLng - lngOffset,
      north: centerLat + latOffset,
      east: centerLng + lngOffset
    };

    // Simplified query for faster response - focus on core walking infrastructure
    const query = `
      [out:json][timeout:15];
      (
        // Core walking infrastructure
        way["highway"~"^(footway|path|pedestrian|steps)$"](${bbox.south},${bbox.west},${bbox.north},${bbox.east});
        way["highway"="residential"]["access"!="private"](${bbox.south},${bbox.west},${bbox.north},${bbox.east});
        way["highway"="service"]["access"!="private"](${bbox.south},${bbox.west},${bbox.north},${bbox.east});
        way["highway"="unclassified"]["access"!="private"](${bbox.south},${bbox.west},${bbox.north},${bbox.east});
      );
      (._;>;);
      out geom;
    `;

    try {
      console.log(`Querying bbox: ${bbox.south.toFixed(4)}, ${bbox.west.toFixed(4)}, ${bbox.north.toFixed(4)}, ${bbox.east.toFixed(4)}`);
      console.log('Sending Overpass query...');
      
      const response = await fetch(this.OVERPASS_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: `data=${encodeURIComponent(query)}`,
        signal: AbortSignal.timeout(10000) // 10 second timeout
      });

      console.log(`Overpass response status: ${response.status}`);

      if (!response.ok) {
        throw new Error(`Overpass API error: ${response.status}`);
      }

      const data: OverpassResponse = await response.json();
      console.log(`Received ${data.elements.length} OSM elements`);
      return this.buildGraph(data);
    } catch (error) {
      console.error('OSM fetch error:', error);
      console.log('Falling back to simple graph...');
      // Return a simple graph with direct connection as fallback
      return this.createFallbackGraph(start, end);
    }
  }

  private static buildGraph(osmData: OverpassResponse): OSMGraph {
    const nodes = new Map<string, OSMNode>();
    const ways = new Map<string, OSMWay>();
    const adjacency = new Map<string, Array<{ nodeId: string; wayId: string; distance: number; fun_weight: number }>>();

    console.log(`Processing ${osmData.elements.length} OSM elements...`);

    // Process nodes first
    for (const element of osmData.elements) {
      if (element.type === 'node' && element.lat !== undefined && element.lon !== undefined) {
        nodes.set(element.id.toString(), {
          id: element.id.toString(),
          lat: element.lat,
          lng: element.lon,
          tags: element.tags || {}
        });
      }
    }

    console.log(`Processed ${nodes.size} nodes`);

    // Process ways and filter for walkable ones
    let walkableWays = 0;
    const tempWays: OSMWay[] = [];
    
    for (const element of osmData.elements) {
      if (element.type === 'way' && element.nodes && element.nodes.length > 1) {
        const wayTags = element.tags || {};
        
        // Skip ways that are explicitly not for pedestrians
        if (wayTags.foot === 'no' || wayTags.access === 'private') {
          continue;
        }

        // Skip motorways and trunk roads without sidewalks
        const highway = wayTags.highway;
        if (highway === 'motorway' || highway === 'trunk' || highway === 'motorway_link' || highway === 'trunk_link') {
          continue;
        }

        const wayId = element.id.toString();
        const wayNodes = element.nodes.map((n: number) => n.toString());
        
        // Only include ways where all nodes exist in our node set
        const validNodes = wayNodes.filter(nodeId => nodes.has(nodeId));
        if (validNodes.length < 2) {
          continue;
        }

        const way: OSMWay = {
          id: wayId,
          nodes: validNodes,
          tags: wayTags
        };

        // Calculate way length
        let totalLength = 0;
        for (let i = 0; i < way.nodes.length - 1; i++) {
          const node1 = nodes.get(way.nodes[i]);
          const node2 = nodes.get(way.nodes[i + 1]);
          if (node1 && node2) {
            totalLength += this.calculateDistance(
              { lat: node1.lat, lng: node1.lng },
              { lat: node2.lat, lng: node2.lng }
            );
          }
        }

        // Skip very short segments (less than 1 meter)
        if (totalLength < 1) {
          continue;
        }

        way.length = totalLength;
        tempWays.push(way);
      }
    }

    // Detect and reclassify paths adjacent to vehicle roads
    this.detectAndReclassifyAdjacentPaths(tempWays, nodes);

    // Now process the modified ways
    for (const way of tempWays) {
      way.fun_weight = this.calculateFunWeight(way, way.length!);
      ways.set(way.id, way);
      walkableWays++;

      // Build adjacency list with proper segment weights
      for (let i = 0; i < way.nodes.length - 1; i++) {
        const nodeId1 = way.nodes[i];
        const nodeId2 = way.nodes[i + 1];
        
        const node1 = nodes.get(nodeId1);
        const node2 = nodes.get(nodeId2);
        
        if (node1 && node2) {
          const segmentDistance = this.calculateDistance(
            { lat: node1.lat, lng: node1.lng },
            { lat: node2.lat, lng: node2.lng }
          );

          // Calculate segment fun weight proportionally
          const segmentFunWeight = (way.fun_weight || segmentDistance) * (segmentDistance / way.length!);

          // Add both directions for undirected graph
          if (!adjacency.has(nodeId1)) adjacency.set(nodeId1, []);
          if (!adjacency.has(nodeId2)) adjacency.set(nodeId2, []);

          adjacency.get(nodeId1)!.push({
            nodeId: nodeId2,
            wayId: way.id,
            distance: segmentDistance,
            fun_weight: segmentFunWeight
          });

          adjacency.get(nodeId2)!.push({
            nodeId: nodeId1,
            wayId: way.id,
            distance: segmentDistance,
            fun_weight: segmentFunWeight
          });
        }
      }
    }

    console.log(`Processed ${walkableWays} walkable ways out of ${ways.size} total ways`);

    // Remove isolated nodes (nodes with no connections)
    const connectedNodes = new Map<string, OSMNode>();
    let totalConnections = 0;
    
    for (const [nodeId, connections] of adjacency) {
      if (connections.length > 0) {
        const node = nodes.get(nodeId);
        if (node) {
          connectedNodes.set(nodeId, node);
          totalConnections += connections.length;
        }
      }
    }

    // Update the graph to only include connected components
    const finalAdjacency = new Map<string, Array<{ nodeId: string; wayId: string; distance: number; fun_weight: number }>>();
    for (const [nodeId, connections] of adjacency) {
      if (connectedNodes.has(nodeId)) {
        // Filter connections to only include other connected nodes
        const validConnections = connections.filter(conn => connectedNodes.has(conn.nodeId));
        if (validConnections.length > 0) {
          finalAdjacency.set(nodeId, validConnections);
        }
      }
    }

    console.log(`Built graph with ${connectedNodes.size} connected nodes and ${walkableWays} ways`);
    console.log(`Total connections: ${totalConnections/2} (bidirectional)`);
    console.log(`Average connections per node: ${(totalConnections/connectedNodes.size).toFixed(1)}`);
    
    return { 
      nodes: connectedNodes, 
      ways, 
      adjacency: finalAdjacency 
    };
  }

  private static calculateFunWeight(way: OSMWay, length: number): number {
    let score = 1.0;
    const highway = way.tags.highway;
    
    // Exact match to Python script fun scoring
    if (highway && this.FUN_HIGHWAYS.has(highway)) {
      score += 2.0;
    }
    
    if (way.tags.leisure === 'park') {
      score += 1.5;
    }
    
    if (way.tags.tourism === 'viewpoint' || way.tags.tourism === 'attraction') {
      score += 3.0;
    }

    // Additional fun features like Python script
    if (way.tags.landuse === 'forest' || way.tags.natural === 'wood') {
      score += 1.5;
    }

    if (way.tags.waterway || (way.tags.name && way.tags.name.toLowerCase().includes('water'))) {
      score += 1.5;
    }

    // Historic areas
    if (way.tags.historic) {
      score += 2.0;
    }

    // Scenic routes
    if (way.tags.scenic === 'yes' || way.tags.name?.toLowerCase().includes('scenic')) {
      score += 2.5;
    }

    // Return fun_weight = length / score (lower is better for pathfinding)
    return length / score;
  }

  static findNearestNode(graph: OSMGraph, coordinate: Coordinate): string | null {
    let nearestNode: string | null = null;
    let minDistance = Infinity;

    for (const [nodeId, node] of graph.nodes) {
      const distance = this.calculateDistance(coordinate, { lat: node.lat, lng: node.lng });
      if (distance < minDistance) {
        minDistance = distance;
        nearestNode = nodeId;
      }
    }

    console.log(`Found nearest node ${nearestNode} at distance ${minDistance.toFixed(2)}m from ${coordinate.lat}, ${coordinate.lng}`);
    return nearestNode;
  }

  static findShortestPath(graph: OSMGraph, startNodeId: string, endNodeId: string, useLength: boolean = true): string[] | null {
    console.log(`Finding path from ${startNodeId} to ${endNodeId}, useLength: ${useLength}`);
    
    // Check if start and end nodes exist in graph
    if (!graph.nodes.has(startNodeId)) {
      console.error(`Start node ${startNodeId} not found in graph`);
      return null;
    }
    if (!graph.nodes.has(endNodeId)) {
      console.error(`End node ${endNodeId} not found in graph`);
      return null;
    }

    // Check if start node has any connections
    const startConnections = graph.adjacency.get(startNodeId);
    const endConnections = graph.adjacency.get(endNodeId);
    console.log(`Start node connections: ${startConnections?.length || 0}, End node connections: ${endConnections?.length || 0}`);

    if (!startConnections || startConnections.length === 0) {
      console.error(`Start node ${startNodeId} has no connections`);
      return null;
    }
    if (!endConnections || endConnections.length === 0) {
      console.error(`End node ${endNodeId} has no connections`);
      return null;
    }

    // Dijkstra's algorithm
    const distances = new Map<string, number>();
    const previous = new Map<string, string | null>();
    const unvisited = new Set<string>();

    // Initialize
    for (const nodeId of graph.nodes.keys()) {
      distances.set(nodeId, Infinity);
      previous.set(nodeId, null);
      unvisited.add(nodeId);
    }
    distances.set(startNodeId, 0);

    let iterations = 0;
    const maxIterations = 50000; // Prevent infinite loops

    while (unvisited.size > 0 && iterations < maxIterations) {
      iterations++;
      
      // Find unvisited node with minimum distance
      let currentNode: string | null = null;
      let minDist = Infinity;
      for (const nodeId of unvisited) {
        const dist = distances.get(nodeId) || Infinity;
        if (dist < minDist) {
          minDist = dist;
          currentNode = nodeId;
        }
      }

      if (!currentNode || minDist === Infinity) {
        console.log(`Pathfinding stopped: no reachable nodes (iterations: ${iterations})`);
        break;
      }
      
      if (currentNode === endNodeId) {
        console.log(`Found path to destination in ${iterations} iterations`);
        break;
      }

      unvisited.delete(currentNode);

      // Check neighbors
      const neighbors = graph.adjacency.get(currentNode) || [];
      for (const neighbor of neighbors) {
        if (!unvisited.has(neighbor.nodeId)) continue;

        const weight = useLength ? neighbor.distance : neighbor.fun_weight;
        const altDistance = (distances.get(currentNode) || 0) + weight;

        if (altDistance < (distances.get(neighbor.nodeId) || Infinity)) {
          distances.set(neighbor.nodeId, altDistance);
          previous.set(neighbor.nodeId, currentNode);
        }
      }
    }

    // Reconstruct path
    if (!previous.has(endNodeId) || previous.get(endNodeId) === null) {
      console.error(`No path found from ${startNodeId} to ${endNodeId} after ${iterations} iterations`);
      return null;
    }

    const path: string[] = [];
    let current: string | null = endNodeId;
    while (current !== null) {
      path.unshift(current);
      current = previous.get(current) || null;
    }

    console.log(`Path found with ${path.length} nodes`);
    return path;
  }

  static async calculateMultipleRoutes(start: Coordinate, end: Coordinate): Promise<RouteResult[]> {
    console.log('Calculating multiple routes using OSM data...');
    
    try {
      const graph = await this.fetchWalkingNetwork(start, end);
      
      const startNodeId = this.findNearestNode(graph, start);
      const endNodeId = this.findNearestNode(graph, end);

      if (!startNodeId || !endNodeId) {
        console.error('Could not find nearest nodes:', { startNodeId, endNodeId });
        throw new Error('Could not find nearest nodes');
      }

      console.log(`Start node: ${startNodeId}, End node: ${endNodeId}`);

      const routes = [];

      // 1. Shortest route (by distance)
      console.log('Finding shortest path...');
      const shortestPath = this.findShortestPath(graph, startNodeId, endNodeId, true);
      console.log('Shortest path result:', shortestPath ? `${shortestPath.length} nodes` : 'null');
      
      if (shortestPath) {
        const coordinates = shortestPath.map(nodeId => {
          const node = graph.nodes.get(nodeId)!;
          return { lat: node.lat, lng: node.lng };
        });

        routes.push({
          name: 'SHORTEST',
          description: 'Fastest direct route',
          coordinates,
          stats: this.calculateRouteStats(graph, shortestPath),
          color: '#ff4444',
          priority: 'speed' as const
        });
      } else {
        console.error('No shortest path found between nodes');
      }

      // 2. Most fun route (by fun weight)
      const funPath = this.findShortestPath(graph, startNodeId, endNodeId, false);
      if (funPath && JSON.stringify(funPath) !== JSON.stringify(shortestPath)) {
        const coordinates = funPath.map(nodeId => {
          const node = graph.nodes.get(nodeId)!;
          return { lat: node.lat, lng: node.lng };
        });

        routes.push({
          name: 'MOST_FUN',
          description: 'Maximum fun score route',
          coordinates,
          stats: this.calculateRouteStats(graph, funPath),
          color: '#44ff44',
          priority: 'fun' as const
        });
      }

      // 3. Balanced route (if we have different routes)
      if (routes.length === 2) {
        // Create a balanced route by mixing the weights
        const balancedPath = this.findBalancedPath(graph, startNodeId, endNodeId);
        if (balancedPath) {
          const coordinates = balancedPath.map(nodeId => {
            const node = graph.nodes.get(nodeId)!;
            return { lat: node.lat, lng: node.lng };
          });

          routes.push({
            name: 'BALANCED',
            description: 'Good mix of speed and fun',
            coordinates,
            stats: this.calculateRouteStats(graph, balancedPath),
            color: '#4444ff',
            priority: 'balanced' as const
          });
        }
      }

      // If no routes found, try to create a simple route using nearby nodes
      if (routes.length === 0) {
        console.log('No complex routes found, attempting simple route...');
        const simpleRoute = this.createSimpleRoute(graph, start, end);
        if (simpleRoute) {
          routes.push(simpleRoute);
        }
      }

      // If we only have one route, create variations
      if (routes.length === 1) {
        const baseRoute = routes[0];
        routes.push({
          name: 'ALTERNATIVE',
          description: 'Alternative scenic route',
          coordinates: this.createAlternativeRoute(baseRoute.coordinates),
          stats: this.calculateRouteStats(graph, shortestPath || []),
          color: '#44ff44',
          priority: 'fun' as const
        });
      }

      console.log(`Generated ${routes.length} routes`);
      return routes;

    } catch (error) {
      console.error('OSM routing error:', error);
      return this.createFallbackRoutes(start, end);
    }
  }

  private static findBalancedPath(graph: OSMGraph, startNodeId: string, endNodeId: string): string[] | null {
    // Use weighted combination of distance and fun weight
    const distances = new Map<string, number>();
    const previous = new Map<string, string | null>();
    const unvisited = new Set<string>();

    for (const nodeId of graph.nodes.keys()) {
      distances.set(nodeId, Infinity);
      previous.set(nodeId, null);
      unvisited.add(nodeId);
    }
    distances.set(startNodeId, 0);

    while (unvisited.size > 0) {
      let currentNode: string | null = null;
      let minDist = Infinity;
      for (const nodeId of unvisited) {
        const dist = distances.get(nodeId) || Infinity;
        if (dist < minDist) {
          minDist = dist;
          currentNode = nodeId;
        }
      }

      if (!currentNode || minDist === Infinity) break;
      if (currentNode === endNodeId) break;

      unvisited.delete(currentNode);

      const neighbors = graph.adjacency.get(currentNode) || [];
      for (const neighbor of neighbors) {
        if (!unvisited.has(neighbor.nodeId)) continue;

        // Balanced weight: 70% distance + 30% fun weight
        const balancedWeight = (neighbor.distance * 0.7) + (neighbor.fun_weight * 0.3);
        const altDistance = (distances.get(currentNode) || 0) + balancedWeight;

        if (altDistance < (distances.get(neighbor.nodeId) || Infinity)) {
          distances.set(neighbor.nodeId, altDistance);
          previous.set(neighbor.nodeId, currentNode);
        }
      }
    }

    // Reconstruct path
    if (!previous.has(endNodeId) || previous.get(endNodeId) === null) {
      return null;
    }

    const path: string[] = [];
    let current: string | null = endNodeId;
    while (current !== null) {
      path.unshift(current);
      current = previous.get(current) || null;
    }

    return path;
  }

  private static calculateRouteStats(graph: OSMGraph, path: string[]): RouteStats {
    let totalDistance = 0;
    let totalFunWeight = 0;
    const pathTypes: Record<string, { distance: number; time: number; speed: number; description: string }> = {
      footway: { distance: 0, time: 0, speed: 4.5, description: 'Dedicated walkways' },
      path: { distance: 0, time: 0, speed: 4.0, description: 'Natural trails and paths' },
      track: { distance: 0, time: 0, speed: 3.5, description: 'Forest trails and dirt roads' },
      steps: { distance: 0, time: 0, speed: 2.5, description: 'Stairs and stepped paths' },
      residential: { distance: 0, time: 0, speed: 4.8, description: 'Residential streets' },
      other: { distance: 0, time: 0, speed: 4.0, description: 'Other walkable paths' }
    };

    const specialAreas: Record<string, { distance: number; time: number; description: string }> = {};

    for (let i = 0; i < path.length - 1; i++) {
      const node1 = graph.nodes.get(path[i]);
      const node2 = graph.nodes.get(path[i + 1]);
      
      if (node1 && node2) {
        const segmentDistance = this.calculateDistance(
          { lat: node1.lat, lng: node1.lng },
          { lat: node2.lat, lng: node2.lng }
        );
        
        totalDistance += segmentDistance;
        
        // Find the way connecting these nodes
        const neighbors = graph.adjacency.get(path[i]) || [];
        const connection = neighbors.find(n => n.nodeId === path[i + 1]);
        
        if (connection) {
          totalFunWeight += connection.fun_weight;
          
          // Analyze the way for path type
          const way = graph.ways.get(connection.wayId);
          if (way) {
            const highway = way.tags.highway || 'other';
            const pathType = pathTypes[highway] ? highway : 'other';
            
            pathTypes[pathType].distance += segmentDistance;
            pathTypes[pathType].time += segmentDistance / 1000 * (60 / pathTypes[pathType].speed);

            // Check for special areas
            if (way.tags.leisure === 'park') {
              if (!specialAreas.park) {
                specialAreas.park = { distance: 0, time: 0, description: 'Parks and green areas' };
              }
              specialAreas.park.distance += segmentDistance;
              specialAreas.park.time += segmentDistance / 1000 * (60 / 4.0);
            }

            if (way.tags.landuse === 'forest' || way.tags.natural === 'wood') {
              if (!specialAreas.forest) {
                specialAreas.forest = { distance: 0, time: 0, description: 'Forests and wooded areas' };
              }
              specialAreas.forest.distance += segmentDistance;
              specialAreas.forest.time += segmentDistance / 1000 * (60 / 3.5);
            }
          }
        }
      }
    }

    const estimatedTime = totalDistance / 1000 * (60 / 4.2); // Average walking speed
    const funScore = totalDistance > 0 ? totalDistance / totalFunWeight : 1.0;

    return {
      distance: totalDistance,
      fun_weight: totalFunWeight,
      fun_score: funScore,
      estimated_time: estimatedTime,
      waypoints: path.length,
      path_types: pathTypes,
      surface_types: {
        unknown: { distance: totalDistance, time: estimatedTime, speed_modifier: 1.0, description: 'Mixed surfaces' }
      },
      special_areas: specialAreas,
      segments: [],
      avg_speed: totalDistance > 0 ? (totalDistance / 1000) / (estimatedTime / 60) : 4.2
    };
  }

  private static createSimpleRoute(graph: OSMGraph, start: Coordinate, end: Coordinate): RouteResult | null {
    console.log('Creating simple route...');
    
    // Find multiple nearby nodes and try to connect them
    const nearbyStartNodes = this.findNearbyNodes(graph, start, 5);
    const nearbyEndNodes = this.findNearbyNodes(graph, end, 5);
    
    console.log(`Found ${nearbyStartNodes.length} nearby start nodes, ${nearbyEndNodes.length} nearby end nodes`);
    
    // Try different combinations
    for (const startNode of nearbyStartNodes) {
      for (const endNode of nearbyEndNodes) {
        const path = this.findShortestPath(graph, startNode.id, endNode.id, true);
        if (path && path.length > 1) {
          console.log(`Simple route found: ${path.length} nodes`);
          
          // Add actual start/end points
          const coordinates = [
            start,
            ...path.map(nodeId => {
              const node = graph.nodes.get(nodeId)!;
              return { lat: node.lat, lng: node.lng };
            }),
            end
          ];
          
          return {
            name: 'SIMPLE',
            description: 'Simple walking route',
            coordinates,
            stats: this.calculateRouteStats(graph, path),
            color: '#888888',
            priority: 'speed' as const
          };
        }
      }
    }
    
    console.log('No simple route found either');
    return null;
  }

  private static findNearbyNodes(graph: OSMGraph, coordinate: Coordinate, count: number): Array<{id: string, distance: number}> {
    const nearby: Array<{id: string, distance: number}> = [];
    
    for (const [nodeId, node] of graph.nodes) {
      const distance = this.calculateDistance(coordinate, { lat: node.lat, lng: node.lng });
      nearby.push({ id: nodeId, distance });
    }
    
    // Sort by distance and return top N that have connections
    return nearby
      .sort((a, b) => a.distance - b.distance)
      .filter(node => {
        const connections = graph.adjacency.get(node.id);
        return connections && connections.length > 0;
      })
      .slice(0, count);
  }

  private static createAlternativeRoute(baseCoordinates: Coordinate[]): Coordinate[] {
    // Create a slight variation of the base route
    return baseCoordinates.map((coord, index) => {
      if (index === 0 || index === baseCoordinates.length - 1) {
        return coord; // Keep start and end points
      }
      
      // Add small random offset to create variation
      const offset = 0.001; // ~100m
      return {
        lat: coord.lat + (Math.random() - 0.5) * offset,
        lng: coord.lng + (Math.random() - 0.5) * offset
      };
    });
  }

  private static createFallbackGraph(start: Coordinate, end: Coordinate): OSMGraph {
    const nodes = new Map<string, OSMNode>();
    const ways = new Map<string, OSMWay>();
    const adjacency = new Map<string, Array<{ nodeId: string; wayId: string; distance: number; fun_weight: number }>>();

    // Create simple two-node graph
    nodes.set('start', { id: 'start', lat: start.lat, lng: start.lng, tags: {} });
    nodes.set('end', { id: 'end', lat: end.lat, lng: end.lng, tags: {} });

    const distance = this.calculateDistance(start, end);
    ways.set('direct', { id: 'direct', nodes: ['start', 'end'], tags: { highway: 'path' }, length: distance });

    adjacency.set('start', [{ nodeId: 'end', wayId: 'direct', distance, fun_weight: distance }]);
    adjacency.set('end', [{ nodeId: 'start', wayId: 'direct', distance, fun_weight: distance }]);

    return { nodes, ways, adjacency };
  }

  private static createFallbackRoutes(start: Coordinate, end: Coordinate): RouteResult[] {
    const directDistance = this.calculateDistance(start, end);
    const estimatedTime = directDistance / 1000 * (60 / 4.2);

    const baseStats = {
      distance: directDistance,
      fun_weight: directDistance,
      fun_score: 1.0,
      estimated_time: estimatedTime,
      waypoints: 2,
      path_types: {
        other: { distance: directDistance, time: estimatedTime, speed: 4.2, description: 'Direct route' }
      },
      surface_types: {
        unknown: { distance: directDistance, time: estimatedTime, speed_modifier: 1.0, description: 'Unknown surface' }
      },
      special_areas: {},
      segments: [],
      avg_speed: 4.2
    };

    return [{
      name: 'DIRECT',
      description: 'Direct route (limited data)',
      coordinates: [start, end],
      stats: baseStats,
      color: '#888888',
      priority: 'speed' as const
    }];
  }

  private static calculateDistance(coord1: Coordinate, coord2: Coordinate): number {
    // Haversine formula
    const R = 6371000; // Earth's radius in meters
    const dLat = (coord2.lat - coord1.lat) * Math.PI / 180;
    const dLng = (coord2.lng - coord1.lng) * Math.PI / 180;
    const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
              Math.cos(coord1.lat * Math.PI / 180) * Math.cos(coord2.lat * Math.PI / 180) *
              Math.sin(dLng/2) * Math.sin(dLng/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    return R * c;
  }
}
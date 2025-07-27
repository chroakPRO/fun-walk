'use client';

import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import RouteMap from '@/components/RouteMap';
import RouteComparison from '@/components/RouteComparison';
import AddressInput from '@/components/AddressInput';
import RouteActions from '@/components/RouteActions';
import { Route, Coordinate, RouteRequest, RouteResponse } from '@/types/route';
import { MapPin, Navigation, Loader2, MapIcon } from 'lucide-react';

export default function ClientApp() {
  const [start, setStart] = useState<Coordinate>({ lat: 58.508594, lng: 15.487358 });
  const [end, setEnd] = useState<Coordinate>({ lat: 58.490666, lng: 15.498153 });
  const [startInput, setStartInput] = useState<string>(`${58.508594}, ${15.487358}`);
  const [endInput, setEndInput] = useState<string>(`${58.490666}, ${15.498153}`);
  const [routes, setRoutes] = useState<Route[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedRoute, setSelectedRoute] = useState<Route | null>(null);

  // Load coordinates from URL parameters on mount
  useEffect(() => {
    if (typeof window === 'undefined') return;
    
    const urlParams = new URLSearchParams(window.location.search);
    const startParam = urlParams.get('start');
    const endParam = urlParams.get('end');

    if (startParam) {
      const [lat, lng] = startParam.split(',').map(Number);
      if (!isNaN(lat) && !isNaN(lng)) {
        setStart({ lat, lng });
      }
    }

    if (endParam) {
      const [lat, lng] = endParam.split(',').map(Number);
      if (!isNaN(lat) && !isNaN(lng)) {
        setEnd({ lat, lng });
      }
    }
  }, []);

  // Keep coordinate input fields in sync when start/end change
  useEffect(() => {
    setStartInput(`${start.lat}, ${start.lng}`);
  }, [start]);

  useEffect(() => {
    setEndInput(`${end.lat}, ${end.lng}`);
  }, [end]);

  const calculateRoutes = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const request: RouteRequest = { start, end };
      const response = await fetch('/api/routes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request)
      });
      
      const data: RouteResponse = await response.json();
      
      if (data.success) {
        setRoutes(data.routes);
        if (data.routes.length > 0) {
          setSelectedRoute(data.routes[0]);
        }
      } else {
        setError(data.error || 'Failed to calculate routes');
      }
    } catch (err) {
      setError('Network error occurred');
      console.error('Route calculation error:', err);
    } finally {
      setLoading(false);
    }
  };

  const useCurrentLocation = () => {
    if ('geolocation' in navigator) {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          setStart({
            lat: position.coords.latitude,
            lng: position.coords.longitude
          });
        },
        (error) => {
          console.error('Geolocation error:', error);
          setError('Could not get current location');
        }
      );
    } else {
      setError('Geolocation is not supported by this browser');
    }
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b bg-card">
        <div className="container mx-auto px-4 py-6">
          <div className="flex items-center gap-3">
            <Navigation className="w-8 h-8 text-primary" />
            <div>
              <h1 className="text-3xl font-bold">Fun Path Planner</h1>
              <p className="text-muted-foreground">Find the most enjoyable walking routes</p>
            </div>
          </div>
        </div>
      </header>

      <div className="container mx-auto px-4 py-8">
        <div className="grid lg:grid-cols-3 gap-8">
          {/* Input Panel */}
          <div className="lg:col-span-1 space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <MapPin className="w-5 h-5" />
                  Route Planning
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Start location */}
                <div className="space-y-2">
                  <AddressInput
                    label="Start Location"
                    placeholder="Enter start address or coordinates"
                    onLocationSelect={setStart}
                  />
                  <Input
                    placeholder="Latitude, Longitude"
                    value={startInput}
                    onChange={(e) => {
                      const value = e.target.value;
                      setStartInput(value);
                      const parts = value.split(/[,\s]+/).map(p => p.trim());
                      if (parts.length >= 2) {
                        const lat = parseFloat(parts[0]);
                        const lng = parseFloat(parts[1]);
                        if (!isNaN(lat) && !isNaN(lng)) {
                          setStart({ lat, lng });
                        }
                      }
                    }}
                  />
                  <Button 
                    variant="outline" 
                    size="sm" 
                    onClick={useCurrentLocation}
                    className="w-full"
                  >
                    Use Current Location
                  </Button>
                </div>

                {/* End location */}
                <div className="space-y-2">
                  <AddressInput
                    label="Destination"
                    placeholder="Enter destination address or coordinates"
                    onLocationSelect={setEnd}
                  />
                  <Input
                    placeholder="Latitude, Longitude"
                    value={endInput}
                    onChange={(e) => {
                      const value = e.target.value;
                      setEndInput(value);
                      const parts = value.split(/[,\s]+/).map(p => p.trim());
                      if (parts.length >= 2) {
                        const lat = parseFloat(parts[0]);
                        const lng = parseFloat(parts[1]);
                        if (!isNaN(lat) && !isNaN(lng)) {
                          setEnd({ lat, lng });
                        }
                      }
                    }}
                  />
                </div>

                {/* Calculate button */}
                <Button 
                  onClick={calculateRoutes} 
                  disabled={loading}
                  className="w-full"
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Calculating Routes...
                    </>
                  ) : (
                    'Calculate Fun Routes'
                  )}
                </Button>

                {error && (
                  <div className="text-sm text-destructive bg-destructive/10 p-3 rounded">
                    {error}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Quick stats */}
            {routes.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Quick Stats</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="text-sm">
                    <div className="flex justify-between">
                      <span>Routes found:</span>
                      <span className="font-semibold">{routes.length}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Fastest route:</span>
                      <span className="font-semibold">
                        {Math.min(...routes.map(r => r.stats.estimated_time)).toFixed(0)}min
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>Most fun score:</span>
                      <span className="font-semibold">
                        {Math.max(...routes.map(r => r.stats.fun_score)).toFixed(2)}
                      </span>
                    </div>
                  </div>
                  
                  {/* Route selection for actions */}
                  <div className="pt-2 border-t">
                    <Label className="text-sm">Select route for actions:</Label>
                    <div className="grid gap-1 mt-1">
                      {routes.map((route) => (
                        <Button
                          key={route.name}
                          variant={selectedRoute?.name === route.name ? "default" : "outline"}
                          size="sm"
                          onClick={() => setSelectedRoute(route)}
                          className="justify-start text-xs"
                        >
                          <div 
                            className="w-3 h-3 rounded mr-2" 
                            style={{ backgroundColor: route.color }}
                          />
                          {route.name}
                          {route.name === 'PARK_HUNTER' && (
                            <span className="ml-2 text-green-600 text-xs">🌲</span>
                          )}
                        </Button>
                      ))}
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Route Actions */}
            {selectedRoute && (
              <RouteActions route={selectedRoute} />
            )}
          </div>

          {/* Main content */}
          <div className="lg:col-span-2">
            <Tabs defaultValue="map" className="w-full">
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="map">Interactive Map</TabsTrigger>
                <TabsTrigger value="comparison">Route Comparison</TabsTrigger>
                <TabsTrigger value="analysis">Detailed Analysis</TabsTrigger>
              </TabsList>
              
              <TabsContent value="map" className="space-y-4">
                <Card>
                  <CardContent className="p-0">
                    {routes.length > 0 ? (
                      <RouteMap 
                        routes={routes} 
                        start={start} 
                        end={end}
                        className="h-[600px]"
                      />
                    ) : (
                      <div className="h-[600px] flex items-center justify-center text-muted-foreground">
                        <div className="text-center">
                          <MapPin className="w-12 h-12 mx-auto mb-4 opacity-50" />
                          <p>Enter coordinates and calculate routes to see the map</p>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="comparison" className="space-y-4">
                {routes.length > 0 ? (
                  <RouteComparison routes={routes} />
                ) : (
                  <Card>
                    <CardContent className="py-12">
                      <div className="text-center text-muted-foreground">
                        <Navigation className="w-12 h-12 mx-auto mb-4 opacity-50" />
                        <p>Calculate routes to see detailed comparison</p>
                      </div>
                    </CardContent>
                  </Card>
                )}
              </TabsContent>

              <TabsContent value="analysis" className="space-y-4">
                {selectedRoute ? (
                  <div className="space-y-4">
                    <Card>
                      <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                          <div 
                            className="w-4 h-4 rounded" 
                            style={{ backgroundColor: selectedRoute.color }}
                          />
                          {selectedRoute.name} Route Analysis
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <p className="text-muted-foreground mb-4">{selectedRoute.description}</p>
                        
                        <div className="grid md:grid-cols-2 gap-6">
                          <div>
                            <h4 className="font-semibold mb-3">Route Statistics</h4>
                            <div className="space-y-2 text-sm">
                              <div className="flex justify-between">
                                <span>Distance:</span>
                                <span>{(selectedRoute.stats.distance / 1000).toFixed(2)} km</span>
                              </div>
                              <div className="flex justify-between">
                                <span>Estimated Time:</span>
                                <span>{Math.round(selectedRoute.stats.estimated_time)} minutes</span>
                              </div>
                              <div className="flex justify-between">
                                <span>Average Speed:</span>
                                <span>{selectedRoute.stats.avg_speed.toFixed(1)} km/h</span>
                              </div>
                              <div className="flex justify-between">
                                <span>Fun Score:</span>
                                <span className="font-semibold text-orange-500">
                                  {selectedRoute.stats.fun_score.toFixed(2)}
                                </span>
                              </div>
                              <div className="flex justify-between">
                                <span>Waypoints:</span>
                                <span>{selectedRoute.stats.waypoints}</span>
                              </div>
                            </div>
                          </div>

                          <div>
                            <h4 className="font-semibold mb-3">Path Breakdown</h4>
                            <div className="space-y-2 text-sm">
                              {Object.entries(selectedRoute.stats.path_types)
                                .filter(([, data]) => data.distance > 0)
                                .map(([type, data]) => (
                                  <div key={type} className="flex justify-between">
                                    <span className="capitalize">{type}:</span>
                                    <span>{Math.round(data.time)} min</span>
                                  </div>
                                ))}
                            </div>
                          </div>
                        </div>

                        {Object.keys(selectedRoute.stats.special_areas).length > 0 && (
                          <div className="mt-6">
                            <h4 className="font-semibold mb-3">Special Areas</h4>
                            <div className="flex flex-wrap gap-2">
                              {Object.entries(selectedRoute.stats.special_areas)
                                .filter(([, data]) => data.distance > 0)
                                .map(([area, data]) => (
                                  <div key={area} className="bg-muted px-3 py-1 rounded-full text-sm">
                                    <span className="capitalize">{area}</span>
                                    <span className="text-muted-foreground ml-1">
                                      ({Math.round(data.time)}min)
                                    </span>
                                  </div>
                                ))}
                            </div>
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  </div>
                ) : (
                  <Card>
                    <CardContent className="py-12">
                      <div className="text-center text-muted-foreground">
                        <MapIcon className="w-12 h-12 mx-auto mb-4 opacity-50" />
                        <p>Select a route to see detailed analysis</p>
                      </div>
                    </CardContent>
                  </Card>
                )}
              </TabsContent>
            </Tabs>
          </div>
        </div>
      </div>
    </div>
  );
}
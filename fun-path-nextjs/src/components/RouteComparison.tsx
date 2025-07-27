'use client';

import { Route } from '@/types/route';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Clock, MapPin, Zap, TrendingUp } from 'lucide-react';

interface RouteComparisonProps {
  routes: Route[];
}

export default function RouteComparison({ routes }: RouteComparisonProps) {
  if (routes.length === 0) return null;

  const sortedByTime = [...routes].sort((a, b) => a.stats.estimated_time - b.stats.estimated_time);
  const sortedByFun = [...routes].sort((a, b) => b.stats.fun_score - a.stats.fun_score);
  const sortedByDistance = [...routes].sort((a, b) => a.stats.distance - b.stats.distance);

  const formatTime = (minutes: number) => `${Math.round(minutes)}min`;
  const formatDistance = (meters: number) => `${(meters / 1000).toFixed(2)}km`;

  return (
    <div className="space-y-6">
      {/* Terminal-style header */}
      <Card className="bg-gray-900 border-green-500 border-2">
        <CardHeader className="pb-3">
          <CardTitle className="font-mono text-green-400 text-sm">
            ┌─[ MULTI-ROUTE COMPARISON ]──────────────────┐
          </CardTitle>
        </CardHeader>
        <CardContent className="font-mono text-xs text-green-400 space-y-1">
          <div className="text-cyan-400">ROUTES COMPUTED: {routes.length}</div>
          {routes.map((route) => (
            <div key={route.name} className="flex items-center space-x-2">
              <div 
                className="w-3 h-3 rounded-sm" 
                style={{ backgroundColor: route.color }}
              />
              <span className="text-yellow-400">
                {route.name}
                {route.name === 'PARK_HUNTER' && <span className="ml-1">🌲</span>}
              </span>
              <span>TIME: {formatTime(route.stats.estimated_time)} | DIST: {formatDistance(route.stats.distance)}</span>
              <span className="text-orange-400">FUN: {route.stats.fun_score.toFixed(2)}</span>
            </div>
          ))}
          <div className="pt-2 text-yellow-400">
            └─────────────────────────────────────────────┘
          </div>
        </CardContent>
      </Card>

      {/* Route cards */}
      <div className="grid gap-4 md:grid-cols-3">
        {routes.map((route) => (
          <Card key={route.name} className="bg-gray-50 dark:bg-gray-800">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg flex items-center gap-2">
                  <div 
                    className="w-4 h-4 rounded" 
                    style={{ backgroundColor: route.color }}
                  />
                  {route.name}
                </CardTitle>
                <Badge variant={route.priority === 'speed' ? 'destructive' : 
                              route.priority === 'fun' ? 'default' : 'secondary'}>
                  {route.priority}
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground">{route.description}</p>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div className="flex items-center gap-2">
                  <Clock className="w-4 h-4 text-blue-500" />
                  <span>{formatTime(route.stats.estimated_time)}</span>
                </div>
                <div className="flex items-center gap-2">
                  <MapPin className="w-4 h-4 text-green-500" />
                  <span>{formatDistance(route.stats.distance)}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Zap className="w-4 h-4 text-orange-500" />
                  <span>{route.stats.fun_score.toFixed(2)}</span>
                </div>
                <div className="flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-purple-500" />
                  <span>{route.stats.avg_speed.toFixed(1)} km/h</span>
                </div>
              </div>

              {/* Path types */}
              <div>
                <h4 className="font-semibold text-sm mb-2">Main Path Types</h4>
                <div className="space-y-1">
                  {Object.entries(route.stats.path_types)
                    .filter(([, data]) => data.distance > 0)
                    .sort(([, a], [, b]) => b.distance - a.distance)
                    .slice(0, 2)
                    .map(([type, data]) => (
                      <div key={type} className="flex justify-between text-xs">
                        <span className="capitalize">{type}</span>
                        <span>{formatTime(data.time)}</span>
                      </div>
                    ))}
                </div>
              </div>

              {/* Special areas */}
              {Object.keys(route.stats.special_areas).length > 0 && (
                <div>
                  <h4 className="font-semibold text-sm mb-2">Special Areas</h4>
                  <div className="flex flex-wrap gap-1">
                    {Object.entries(route.stats.special_areas)
                      .filter(([, data]) => data.distance > 0)
                      .map(([area]) => (
                        <Badge key={area} variant="outline" className="text-xs">
                          {area}
                        </Badge>
                      ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Detailed comparison tabs */}
      <Tabs defaultValue="overview" className="w-full">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="details">Details</TabsTrigger>
          <TabsTrigger value="recommendations">Recommendations</TabsTrigger>
        </TabsList>
        
        <TabsContent value="overview" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Route Rankings</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <h4 className="font-semibold mb-2">Fastest Route</h4>
                <p className="text-sm text-muted-foreground">
                  {sortedByTime[0].name} - {formatTime(sortedByTime[0].stats.estimated_time)}
                </p>
              </div>
              <div>
                <h4 className="font-semibold mb-2">Most Fun Route</h4>
                <p className="text-sm text-muted-foreground">
                  {sortedByFun[0].name} - Fun Score: {sortedByFun[0].stats.fun_score.toFixed(2)}
                </p>
              </div>
              <div>
                <h4 className="font-semibold mb-2">Shortest Route</h4>
                <p className="text-sm text-muted-foreground">
                  {sortedByDistance[0].name} - {formatDistance(sortedByDistance[0].stats.distance)}
                </p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="details" className="space-y-4">
          {routes.map((route) => (
            <Card key={route.name}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <div 
                    className="w-4 h-4 rounded" 
                    style={{ backgroundColor: route.color }}
                  />
                  {route.name} Route Details
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid md:grid-cols-2 gap-4 text-sm">
                  <div>
                    <h4 className="font-semibold mb-2">Path Type Breakdown</h4>
                    {Object.entries(route.stats.path_types)
                      .filter(([, data]) => data.distance > 0)
                      .map(([type, data]) => (
                        <div key={type} className="flex justify-between mb-1">
                          <span className="capitalize">{type}</span>
                          <span>{formatTime(data.time)} ({data.distance.toFixed(0)}m)</span>
                        </div>
                      ))}
                  </div>
                  <div>
                    <h4 className="font-semibold mb-2">Surface Types</h4>
                    {Object.entries(route.stats.surface_types)
                      .filter(([, data]) => data.distance > 0)
                      .map(([type, data]) => (
                        <div key={type} className="flex justify-between mb-1">
                          <span className="capitalize">{type}</span>
                          <span>{formatTime(data.time)}</span>
                        </div>
                      ))}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="recommendations" className="space-y-4">
          <div className="grid gap-4">
            {routes.map((route) => (
              <Card key={route.name}>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <div 
                      className="w-4 h-4 rounded" 
                      style={{ backgroundColor: route.color }}
                    />
                    {route.name} Route
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm mb-2">{route.description}</p>
                  <p className="text-sm text-muted-foreground">
                    Best for: {
                      route.priority === 'speed' ? 'Getting there quickly' :
                      route.priority === 'fun' ? 'Scenic walks and interesting paths' :
                      'Balance of speed and enjoyment'
                    }
                  </p>
                  <div className="mt-2 text-xs text-muted-foreground">
                    {formatTime(route.stats.estimated_time)} • {formatDistance(route.stats.distance)} • 
                    Fun Score: {route.stats.fun_score.toFixed(2)}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
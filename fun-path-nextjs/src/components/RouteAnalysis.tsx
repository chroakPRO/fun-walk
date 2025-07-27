'use client';

import { Route } from '@/types/route';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Clock, MapPin, Zap, TrendingUp, TreePine, Mountain } from 'lucide-react';

interface RouteAnalysisProps {
  route: Route;
}

export default function RouteAnalysis({ route }: RouteAnalysisProps) {
  const formatTime = (minutes: number) => `${Math.round(minutes)}min`;
  const formatDistance = (meters: number) => `${(meters / 1000).toFixed(2)}km`;

  // Calculate percentages for path types
  const totalDistance = route.stats.distance;
  const pathTypeEntries = Object.entries(route.stats.path_types)
    .filter(([, data]) => data.distance > 0)
    .sort(([, a], [, b]) => b.distance - a.distance);

  const surfaceTypeEntries = Object.entries(route.stats.surface_types)
    .filter(([, data]) => data.distance > 0)
    .sort(([, a], [, b]) => b.distance - a.distance);

  const specialAreaEntries = Object.entries(route.stats.special_areas)
    .filter(([, data]) => data.distance > 0)
    .sort(([, a], [, b]) => b.distance - a.distance);

  return (
    <div className="space-y-6">
      {/* Route Overview */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <div 
              className="w-4 h-4 rounded" 
              style={{ backgroundColor: route.color }}
            />
            {route.name} Route Analysis
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-muted-foreground">{route.description}</p>
          
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center">
              <Clock className="w-6 h-6 mx-auto mb-2 text-blue-500" />
              <div className="text-2xl font-bold">{formatTime(route.stats.estimated_time)}</div>
              <div className="text-sm text-muted-foreground">Estimated Time</div>
            </div>
            <div className="text-center">
              <MapPin className="w-6 h-6 mx-auto mb-2 text-green-500" />
              <div className="text-2xl font-bold">{formatDistance(route.stats.distance)}</div>
              <div className="text-sm text-muted-foreground">Distance</div>
            </div>
            <div className="text-center">
              <Zap className="w-6 h-6 mx-auto mb-2 text-orange-500" />
              <div className="text-2xl font-bold">{route.stats.fun_score.toFixed(2)}</div>
              <div className="text-sm text-muted-foreground">Fun Score</div>
            </div>
            <div className="text-center">
              <TrendingUp className="w-6 h-6 mx-auto mb-2 text-purple-500" />
              <div className="text-2xl font-bold">{route.stats.avg_speed.toFixed(1)}</div>
              <div className="text-sm text-muted-foreground">km/h</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Path Type Breakdown */}
      <Card>
        <CardHeader>
          <CardTitle>Path Type Breakdown</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {pathTypeEntries.map(([type, data]) => {
            const percentage = (data.distance / totalDistance) * 100;
            return (
              <div key={type} className="space-y-2">
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-2">
                    <TreePine className="w-4 h-4 text-green-600" />
                    <span className="font-medium capitalize">{type}</span>
                  </div>
                  <div className="text-sm text-muted-foreground">
                    {formatTime(data.time)} • {data.distance.toFixed(0)}m
                  </div>
                </div>
                <Progress value={percentage} className="h-2" />
                <p className="text-xs text-muted-foreground">{data.description}</p>
              </div>
            );
          })}
        </CardContent>
      </Card>

      {/* Surface Types */}
      <Card>
        <CardHeader>
          <CardTitle>Surface Analysis</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {surfaceTypeEntries.map(([type, data]) => {
            const percentage = (data.distance / totalDistance) * 100;
            return (
              <div key={type} className="space-y-2">
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-2">
                    <Mountain className="w-4 h-4 text-gray-600" />
                    <span className="font-medium capitalize">{type}</span>
                    <Badge variant="outline" className="text-xs">
                      {data.speed_modifier}x speed
                    </Badge>
                  </div>
                  <div className="text-sm text-muted-foreground">
                    {formatTime(data.time)}
                  </div>
                </div>
                <Progress value={percentage} className="h-2" />
                <p className="text-xs text-muted-foreground">{data.description}</p>
              </div>
            );
          })}
        </CardContent>
      </Card>

      {/* Special Areas */}
      {specialAreaEntries.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Special Areas & Attractions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {specialAreaEntries.map(([area, data]) => {
              const percentage = (data.distance / totalDistance) * 100;
              return (
                <div key={area} className="space-y-2">
                  <div className="flex justify-between items-center">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 bg-green-500 rounded-full" />
                      <span className="font-medium capitalize">{area}</span>
                    </div>
                    <div className="text-sm text-muted-foreground">
                      {formatTime(data.time)} • {data.distance.toFixed(0)}m
                    </div>
                  </div>
                  <Progress value={percentage} className="h-2" />
                  <p className="text-xs text-muted-foreground">{data.description}</p>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      {/* Route Segments Preview */}
      <Card>
        <CardHeader>
          <CardTitle>Route Segments</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <div className="text-sm text-muted-foreground">
              This route consists of {route.stats.waypoints} waypoints with detailed segment analysis.
            </div>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="font-medium">Total Segments:</span> {route.stats.segments.length}
              </div>
              <div>
                <span className="font-medium">Average Speed:</span> {route.stats.avg_speed.toFixed(1)} km/h
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Recommendations */}
      <Card>
        <CardHeader>
          <CardTitle>Route Recommendations</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div className="flex items-start gap-3">
              <div className="w-2 h-2 bg-blue-500 rounded-full mt-2" />
              <div>
                <p className="font-medium">Best for:</p>
                <p className="text-sm text-muted-foreground">
                  {route.priority === 'speed' ? 'Getting there quickly with minimal detours' :
                   route.priority === 'fun' ? 'Scenic walks with interesting paths and natural areas' :
                   'A good balance between efficiency and enjoyment'}
                </p>
              </div>
            </div>
            
            <div className="flex items-start gap-3">
              <div className="w-2 h-2 bg-green-500 rounded-full mt-2" />
              <div>
                <p className="font-medium">Difficulty:</p>
                <p className="text-sm text-muted-foreground">
                  {route.stats.avg_speed > 4.5 ? 'Easy - mostly paved surfaces' :
                   route.stats.avg_speed > 3.5 ? 'Moderate - mixed surfaces with some trails' :
                   'Challenging - natural trails and varied terrain'}
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <div className="w-2 h-2 bg-orange-500 rounded-full mt-2" />
              <div>
                <p className="font-medium">Highlights:</p>
                <p className="text-sm text-muted-foreground">
                  {specialAreaEntries.length > 0 
                    ? `Passes through ${specialAreaEntries.map(([area]) => area).join(', ')}`
                    : 'Direct route with standard walking paths'}
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
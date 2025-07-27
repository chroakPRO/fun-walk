'use client';

import { Route } from '@/types/route';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { 
  Download, 
  ExternalLink, 
  Share2, 
  Navigation,
  Map,
  FileText
} from 'lucide-react';
import { MapIntegration, RouteExporter } from '@/services/mapIntegration';

interface RouteActionsProps {
  route: Route;
}

export default function RouteActions({ route }: RouteActionsProps) {
  const handleGoogleMaps = () => {
    MapIntegration.openInGoogleMaps(route);
  };

  const handleAppleMaps = () => {
    MapIntegration.openInAppleMaps(route);
  };

  const handleWaze = () => {
    MapIntegration.openInWaze(route);
  };

  const handleShare = () => {
    MapIntegration.shareRoute(route);
  };

  const handleExportGPX = () => {
    RouteExporter.exportAsGPX(route);
  };

  const handleExportKML = () => {
    RouteExporter.exportAsKML(route);
  };

  const handleExportGeoJSON = () => {
    RouteExporter.exportAsGeoJSON(route);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Navigation className="w-5 h-5" />
          Route Actions
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* External Map Apps */}
        <div>
          <h4 className="font-semibold mb-2 text-sm">Open in Map Apps</h4>
          <div className="grid grid-cols-1 gap-2">
            <Button 
              variant="outline" 
              onClick={handleGoogleMaps}
              className="justify-start"
            >
              <Map className="w-4 h-4 mr-2" />
              Google Maps
              <ExternalLink className="w-3 h-3 ml-auto" />
            </Button>
            <Button 
              variant="outline" 
              onClick={handleAppleMaps}
              className="justify-start"
            >
              <Map className="w-4 h-4 mr-2" />
              Apple Maps
              <ExternalLink className="w-3 h-3 ml-auto" />
            </Button>
            <Button 
              variant="outline" 
              onClick={handleWaze}
              className="justify-start"
            >
              <Navigation className="w-4 h-4 mr-2" />
              Waze
              <ExternalLink className="w-3 h-3 ml-auto" />
            </Button>
          </div>
        </div>

        {/* Export Options */}
        <div>
          <h4 className="font-semibold mb-2 text-sm">Export Route</h4>
          <div className="grid grid-cols-1 gap-2">
            <Button 
              variant="outline" 
              onClick={handleExportGPX}
              className="justify-start"
            >
              <Download className="w-4 h-4 mr-2" />
              Download GPX
              <span className="ml-auto text-xs text-muted-foreground">GPS</span>
            </Button>
            <Button 
              variant="outline" 
              onClick={handleExportKML}
              className="justify-start"
            >
              <Download className="w-4 h-4 mr-2" />
              Download KML
              <span className="ml-auto text-xs text-muted-foreground">Google Earth</span>
            </Button>
            <Button 
              variant="outline" 
              onClick={handleExportGeoJSON}
              className="justify-start"
            >
              <FileText className="w-4 h-4 mr-2" />
              Download GeoJSON
              <span className="ml-auto text-xs text-muted-foreground">Data</span>
            </Button>
          </div>
        </div>

        {/* Share */}
        <div>
          <h4 className="font-semibold mb-2 text-sm">Share Route</h4>
          <Button 
            variant="outline" 
            onClick={handleShare}
            className="w-full justify-start"
          >
            <Share2 className="w-4 h-4 mr-2" />
            Share Route Link
          </Button>
        </div>

        {/* Route Info */}
        <div className="pt-2 border-t">
          <div className="text-xs text-muted-foreground space-y-1">
            <div>Distance: {(route.stats.distance / 1000).toFixed(2)} km</div>
            <div>Time: {Math.round(route.stats.estimated_time)} minutes</div>
            <div>Fun Score: {route.stats.fun_score.toFixed(2)}</div>
            <div>Waypoints: {route.stats.waypoints}</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
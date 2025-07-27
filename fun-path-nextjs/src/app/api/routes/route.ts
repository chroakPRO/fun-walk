import { NextRequest, NextResponse } from 'next/server';
import { RouteRequest, RouteResponse } from '@/types/route';
import { RouteEngine } from '@/services/routeEngine';

export async function POST(request: NextRequest) {
  try {
    const body: RouteRequest = await request.json();
    
    if (!body.start || !body.end) {
      return NextResponse.json(
        { success: false, error: 'Start and end coordinates are required' },
        { status: 400 }
      );
    }

    console.log('Calculating routes for:', body.start, 'to', body.end);

    // Use the real routing engine
    const routes = await RouteEngine.calculateMultipleRoutes(body.start, body.end);
    
    const response: RouteResponse = {
      routes,
      success: true
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error('Route calculation error:', error);
    return NextResponse.json(
      { success: false, error: `Failed to calculate routes: ${error instanceof Error ? error.message : 'Unknown error'}` },
      { status: 500 }
    );
  }
}
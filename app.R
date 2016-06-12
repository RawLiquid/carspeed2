library(RPostgreSQL)
library(grid)
library(ggplot2)
library(shiny)
library(scales)
library(Cairo)
library(shinythemes)
library(zoo)
library(plyr)

# TODO: Add statistics table
# TODO: Code to allow range to be be available only for ranges for which there are data entries
# TODO: Option and code to show daily graphs (maybe past week, past month?)
# TODO: Charts initially display data downloaded in vehicles.Rdata (same dir). "Update" button refreshes data and charts

# create a connection
sqlQuery <- function(beginDate, endDate){
# save the password that we can "hide" it as best as we can by collapsing it
  pw <- {
    "Rward0232"
  }
  
  tryCatch({
    # loads the PostgreSQL driver
    drv <- dbDriver("PostgreSQL")
    # creates a connection to the postgres database
    # note that "con" will be used later in each connection to the database
    con <- dbConnect(drv, dbname = "speedcamdb",
                     host = "192.168.1.14", port = 5432,
                     user = "speedcam", password = pw)
    
    # build query
    beginDate <- sprintf("%s 00:00:00", beginDate)
    endDate <- sprintf('%s 23:59:59', endDate)
    query <- sprintf("SELECT * FROM vehicles WHERE datetime >= '%s' AND datetime <= '%s'", beginDate, endDate)
    
    results <- dbGetQuery(con, query)
    
    dbDisconnect(con)
    },
    
    warning = function(w){
      Print("Warning!")
    },
    
    error = function(e){
      results = source(oldData)
    }
  )
  
  return(results)
  
  rm(pw) # removes the password

}

remove_outliers <- function(x, na.rm = TRUE, ...) {
  qnt <- quantile(x, probs=c(.25, .75), na.rm = na.rm, ...)
  H <- 1.5 * IQR(x, na.rm = na.rm)
  y <- x
  y[x < (qnt[1] - H)] <- NA
  y[x > (qnt[2] + H)] <- NA
  y
}

# Make sure there are no duplicate speeds in table (speeds are so precise, there should never be
# any real instances where they are the same)

ui <- fluidPage(
	theme = shinytheme("flatly"),
	#titlePanel("Ridgmar Boulevard Speed Statistics",
		tags$head(tags$link(rel="shortcut icon", href="favicon.ico")),
	headerPanel("Ridgmar Speed Statistics"),
  
	 sidebarLayout(
		sidebarPanel(
			#h1("Ridgmar Speed Statistics"),

			p("A project undertaken to detect and analyze driver speeds on Ridgmar Boulevard in Fort Worth, Texas using a Raspberry Pi, Python, and R."),
			br(),
			p("This project is still under heavy development, and data should not be understood to be accurate."),
			br(),
			#helpText("*** NOTICE: 4/23/2016 - The Air Power Expo has resulted in Soutbound lane blockage on Ridgmar Blvd. Data will reflect this."),
			br(),
			#sliderInput("range", "Time Range (N hours ago - Now)", min = 2, max = 48, value = 4),
			dateRangeInput('range', 'Date range', start = Sys.Date() - 1, min = '2016-01-01'),
			sliderInput("l_span", "Trend Fitting Parameter", min = 0.1, max = 1, value = 0.7),
			
			br(),
			helpText("Display either all data, or data for vehicles travelling above the speed limit."),
			radioButtons("speedOnly", "Data to analyze", c("All" = "all","Speeders Only" = "speeders")),
			
			br(),
			helpText("Enabling auto-update will cause the tool to refresh the data and graphs every minute."),
			radioButtons("autoUpdate", "Auto-Update", c("On" = "TRUE", "Off" = "FALSE")),

			br(),
			helpText("Apply all settings and refresh data and graphs."),
			actionButton("update", label = "Update")
		),
    
		mainPanel("",
			tabsetPanel(
				tabPanel("Daily Plots",
					plotOutput(outputId = "loess"),
					plotOutput(outputId = "speed_dens"),
					plotOutput(outputId = "percentage_speeders"),
					plotOutput(outputId = "time_dens")
				),

				tabPanel("Images",
				         p("This page will host images of vehicles travelling at least 10 mph over speed limit.")
				         ),

				tabPanel("Table",
					tableOutput("table")
				),
			
				tabPanel("About",
					verbatimTextOutput("summaryPage"),
					h4("Summary"),
					p("A tool developed on a Raspberry Pi 2B to detect and analyze traffic speeds on Ridgmar Boulevard in Fort Worth, Texas."),
					p("The code is a modified version of Greg Barbu's CarSpeed code, which relies on the OpenCV (Computer Vision) library for Python.
						The code was modified to allow for output into a PostgreSQL database for data logging and analysis, and for auto-correcting
						when a problem with motion detection occurs (changing light levels wreaks havoc on the system). Planned features include
						vehicle color detection and pedestrian detection."),
					br(),
					p("The code for this project is hosted at"),
					a("https://github.com/minorsecond/carspeed.py"),
					br(),
					br(),
					p("The original code and project description created by Greg can be found at"),
                                        a("https://gregtinkers.wordpress.com/2016/03/25/car-speed-detector/"),
					br(),
					hr(),
					p("Developed by Robert Ross Wardrup using Shiny, R, openCV and Python")
				)
			)
		)
	)
)

server <- function(input, output) {
  options(bitmapType = 'cairo')
  autoInvalidate <- reactiveTimer(60000)

  observe({

	options(scipen=999)
	if(input$autoUpdate=="TRUE"){
		autoInvalidate()
	}
	# Send query
      
	# query the data from postgreSQL
	input$update
	withProgress(message="Updating data...", expr=1)
	vehicles <- sqlQuery(input$range[1], input$range[2])
	vehicles$speed <- remove_outliers(vehicles$speed)
	
	# Create date variable and sequence of days as specified by user
	vehicles$date <- as.Date(vehicles$datetime)
	date_seq <- seq(input$range[1], input$range[2], by = "day")

	# Subset the data based on parameters
	vehicles <- vehicles[ which(vehicles$rating > 4), ]  # Only keep good values
	vehicles <- vehicles[ which(vehicles$rating < 10), ]  # Only keep good values
	
	vehicles <- vehicles[ which(vehicles$speed <= 75), ]
	#vehicles <- vehicles[ which(vehicles$speed >= 20), ]
	#vehicles <- vehicles[ which(vehicles$datetime >= Sys.time() - (input$range * 3600)), ]

	# Subset based on date
	vehicles <- vehicles[ which(vehicles$date %in% date_seq), ]
	
	vehicles$speeding <- ifelse(vehicles$speed>35, as.integer(1),as.integer(0))
	vehicles$count <- 1
	#time <- data.frame(time=format(vehicles$datetime, "%H"), speeders=vehicles$speeding, count = vehicles$count)
	time <- data.frame(time = as.POSIXct(strptime(vehicles$datetime, '%Y-%m-%d %H', tz='CT')), speeders=vehicles$speeding, count = vehicles$count)
	speed_agg <- aggregate(. ~ time, data=time, FUN = sum)
	speed_agg$speed.prop <- (speed_agg$speeders / speed_agg$count)

	table_for_display <- vehicles[ ,c('datetime', 'speed', 'direction', 'speeding')]
	table_for_display <- rename(table_for_display, c('datetime'='Time', 'speed'='Speed', 'direction'='Direction', 'speeding'='Is Speeding'))

	if(input$speedOnly=="speeders"){
		vehicles <- vehicles[ which(vehicles$speeding==1), ]
	}

	output$percentage_speeders <- renderPlot({
		ggplot(speed_agg, aes(x = time, y = speed.prop)) + 
  		geom_point(color="#3498db") +
  		geom_smooth(level=0.99, colour='#c0392b', na.rm=TRUE, span=.5, se=F, cex=0.7, fill='#34495e', alpha = .8) + 
  		xlab("Time") + 
  		ylab("Speeders : Drivers") +
  		ggtitle("Proportion of Speeders to All Drivers") +
		#scale_x_datetime(breaks = date_breaks('2 hour'), minor_breaks=waiver(), date_labels='%A %H:%M') +
      theme_bw() +
      theme(plot.title=element_text(size=20, color="black", margin=margin(10,0,10,0), face="bold"),
      axis.title=element_text(color="black", size=12),
      axis.text=element_text(color="black", size=12),
      panel.border=element_blank(), 
      panel.background = element_blank(),
      panel.grid.minor = element_blank(),  
      panel.grid.major = element_blank())
			})
      
	output$loess <- renderPlot({
		ggplot(vehicles, aes(x = as.POSIXct(strptime(vehicles$datetime, '%Y-%m-%d %H:%M:%S')),y = vehicles$speed)) + 
  		ggtitle("Speed Trend over Time") + 
  		xlab("Time") +
  		ylab("Speed (MPH)") + 
  		geom_smooth(level=.99, span=input$l_span, na.rm=TRUE,show.legend=F, colour='white', cex=.7, fill = '#2c3e50', alpha=0.8) +
  		geom_hline(yintercept = 35, colour = '#c0392b', cex=1.2) +
  		geom_point(aes(color=direction), alpha=0.35, cex=1.5) +
	    scale_colour_manual(name="Direction of Travel", breaks=c('North', 'South'), values=c('#EB9532', '#3498db')) + 
  		theme_bw() + 
  		theme(plot.title=element_text(size=20, color="black", margin=margin(10,0,10,0), face="bold"), 
  		axis.title=element_text(color="black", size=12),
  		axis.text=element_text(color="black", size=12), 
  		panel.border=element_blank(),
  		legend.key=element_blank(),
  		panel.background = element_blank(), 
  		panel.grid.minor = element_blank(),  
  		panel.grid.major = element_blank())
		})

	output$speed_dens <- renderPlot({
		ggplot(vehicles, aes(speed)) +
		geom_density(aes(fill='#34495e'), alpha=0.8 ,trim=TRUE, bw="SJ") + 
		ggtitle("Speed Densities") +
		guides(fill=FALSE) +
		theme_bw() +
		xlab("Speed (MPH)") +
		ylab("Density") +
		geom_vline(xintercept=35, colour='#c0392b', cex=1.2) +
		theme_bw() +
		theme(plot.title=element_text(size=20, color="black", margin=margin(10,0,10,0), face="bold"),
		legend.key = element_blank(),
		axis.title=element_text(color="black", size=12),
		axis.text=element_text(color="black", size=12),
		panel.border=element_blank(),
		panel.background = element_blank(),
		panel.grid.minor = element_blank(),
		panel.grid.major = element_blank())
	})
	
	output$time_dens <- renderPlot({
    ggplot(data=vehicles, aes(datetime)) +
	    geom_density(aes(fill='#27AE60'), alpha=0.8) + 
	    scale_fill_manual(values=c("#349935")) + 
      ggtitle("Time Densities") +
      guides(fill=FALSE) +
      theme_bw() +
      xlab("Time") +
      ylab("Density") +
      theme_bw() +
      theme(plot.title=element_text(size=20, color="black", margin=margin(10,0,10,0), face="bold"),
      legend.key = element_blank(),
      axis.title=element_text(color="black", size=12),
      axis.text=element_text(color="black", size=12),
      panel.border=element_blank(),
      panel.background = element_blank(),
      panel.grid.minor = element_blank(),
      panel.grid.major = element_blank())
	})

	output$table <- renderTable({
		data.frame(table_for_display)

	})
  })
}
shinyApp(ui = ui, server = server)

# install.packages("RPostgreSQL")
library(RPostgreSQL)
library(grid)
library(ggplot2)
library(shiny)
library(scales)
library(Cairo)
library(shinythemes)

# Load pre-existing data
#vehicles <- readRDS("./vehicles.rds")

# TODO: Add statistics table
# TODO: Add histogram showing peak times of speeders
# TODO: Speeders only check box
# TODO: Code to allow range to be be available only for ranges for which there are data entries
# TODO: Option and code to show daily graphs (maybe past week, past month?)
# TODO: Charts initially display data downloaded in vehicles.Rdata (same dir). "Update" button refreshes data and charts

# create a connection
# save the password that we can "hide" it as best as we can by collapsing it
pw <- {
  "Rward0232"
}

# loads the PostgreSQL driver
drv <- dbDriver("PostgreSQL")
# creates a connection to the postgres database
# note that "con" will be used later in each connection to the database
con <- dbConnect(drv, dbname = "speedcamdb",
                 host = "192.168.1.3", port = 5432,
                 user = "speedcam", password = pw)
rm(pw) # removes the password

# Make sure there are no duplicate speeds in table (speeds are so precise, there should never be
# any real instances where they are the same)

ui <- fluidPage(
	tags$head(tags$link(rel="shortcut icon", href="favicon.ico")),
	theme = shinytheme("flatly"),
	#titlePanel("Ridgmar Boulevard Speed Statistics"),
  
	 sidebarLayout(
		sidebarPanel(
			h1("Ridgmar Speed Statistics"),
			#helpText("Click the update button to pull fresh data from the database. Data is only collected during daylight hours - otherwise graphs will be empty."),

			p("A project undertaken to detect and analyze driver speeds on Ridgmar Boulevard in Fort Worth, Texas using a Raspberry Pi, Python, and R."),
			br(),
			br(),
			sliderInput("range", "Time Range (N hours ago - Now)", min = 1, max = 48, value = 12),
			
			br(),
			helpText("Display either all data, or data for vehicles travelling above the speed limit."),
			radioButtons("speedOnly", "Data to analyze", c("All" = "all","Speeders Only" = "speeders")),
			
			br(),
			helpText("Enabling auto-update will cause the tool to refresh the data and graphs every minute."),
			radioButtons("autoUpdate", "Autoupdate", c("On" = "TRUE", "Off" = "FALSE")),

			br(),
			helpText("Apply all settings and refresh data and graphs."),
			actionButton("update", label = "Update")
		),
    
		mainPanel("",
			tabsetPanel(
				tabPanel("Hourly Plots",
					#plotOutput(outputId = "bbox"),
					plotOutput(outputId = "loess"),
					plotOutput(outputId = "hist")
				),

				#tabPanel("Daily Plots"		
				#),

				tabPanel("Table",
					tableOutput("table")
				),
			
				tabPanel("About",
					verbatimTextOutput("summaryPage"),
					h4("Summary"),
					p("A tool developed on a Raspberry Pi 2 B+ to detect and analayze traffic speeds on Ridgmar Boulevard in Fort Worth, Texas."),
					p("The code is a modified version of Greg Barbu's CarSpeed code, which relies on the OpenCV (Computer Vision) library for Python.
						The code was modified to allow for output into a PostgreSQL database for data logging and anlaysis, and for auto-correcting
						when a problem with motion detection occurs (changing light levels wreaks havoc on the system)."),
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
	if(input$autoUpdate=="TRUE"){
		autoInvalidate()
	}
	# Send query
      
	# query the data from postgreSQL
	input$update
	withProgress(message="Updating data...", expr=1)
	original_vehicles <- dbGetQuery(con, "SELECT * from vehicles")
	vehicles <- original_vehicles

	# Subset the data based on parameters
	vehicles <- vehicles[ which(vehicles$rating <= 15), ]  # Only keep good values
	vehicles <- vehicles[ which(vehicles$speed <= 75), ]
	vehicles <- vehicles[ which(vehicles$speed >= 0), ]
	vehicles <- vehicles[ which(vehicles$datetime >= Sys.time() - (input$range * 3600)), ]
	vehicles$speeding <- as.factor(ifelse(vehicles$speed>35, 2,1))

	if(input$speedOnly=="speeders"){
		vehicles <- vehicles[ which(vehicles$speeding==2), ]
	}

	output$bbox <- renderPlot({
		ggplot(vehicles, aes(x = as.factor(as.POSIXct(strptime(vehicles$datetime, '%Y-%m-%d %H'))),
		y = vehicles$speed)) + 
		geom_boxplot(color="#2c3e50") + 
		geom_hline(yintercept = 35, colour = "#c0392b", cex=1.2) +
		xlab("Time") + 
		ylab("Speed (MPH)") +
		ggtitle("Speed Box Plots") +
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
		ggplot(vehicles, aes(x = as.POSIXct(strptime(vehicles$datetime, '%Y-%m-%d %H:%M')),y = vehicles$speed)) + 
		ggtitle("Speed Trend over Time") + 
		#stat_smooth(level = .99, colour='#FFFF99') + 
		#geom_point(alpha=0.4,colour=factor(vehicles$speeding)) + 
		xlab("Time") +
		ylab("Speed (MPH)") + 
		#geom_hline(yintercept = 35, colour = "#377EB8", cex=1.5) + 
		#geom_hline(yintercept = median, colour = "#4DAF4A", cex=1.5) +
		geom_smooth(level=.99, span=0.5, na.rm=TRUE,show.legend=TRUE, colour='white', cex=.7, fill = '#34495e', alpha=0.8) +
		geom_hline(yintercept = 35, colour = '#c0392b', cex=1.2) +
		geom_point(colour="#3498db", alpha=0.4) +
		scale_colour_manual(name="Legend", values=cols) +
		theme_bw() + 
		theme(plot.title=element_text(size=20, color="black", margin=margin(10,0,10,0), face="bold"), 
		axis.title=element_text(color="black", size=12),
		axis.text=element_text(color="black", size=12), 
		panel.border=element_blank(), 
		panel.background = element_blank(), 
		panel.grid.minor = element_blank(),  
		panel.grid.major = element_blank())
		})

	output$hist <- renderPlot({
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

	output$table <- renderTable({
		data.frame(vehicles)

	})
  })
}
shinyApp(ui = ui, server = server)
